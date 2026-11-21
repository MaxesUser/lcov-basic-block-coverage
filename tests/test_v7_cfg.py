import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bb_cfg import parse_ir, attach_cfg
from cfg_graph import collapsed_groups, build_dot, render_one
from verify_instrumentation import verify


class LLVMControlFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'foo.c'
        self.src.write_text('int foo(int x) {\n if (x) return 1;\n return 0;\n}\n')

    def test_phi_references_do_not_create_outgoing_edges(self):
        ir = self.root / 'test.ll'
        ir.write_text(f'''source_filename = "{self.src}"
@pcs = private constant [6 x ptr] [ptr @foo, ptr null, ptr blockaddress(@foo, %other), ptr null, ptr blockaddress(@foo, %end), ptr null], section "__sancov_pcs"
define i32 @foo(i32 %x) !dbg !1 {{
  br i1 true, label %other, label %end, !dbg !11
other:
  br label %end, !dbg !12
end:
  %v = phi i32 [ 1, %other ], [ 0, %entry ], !dbg !13
  ret i32 %v, !dbg !13
}}
!11 = !DILocation(line: 1, column: 1, scope: !1)
!12 = !DILocation(line: 2, column: 1, scope: !1)
!13 = !DILocation(line: 3, column: 1, scope: !1)
''')
        graph = parse_ir(ir)['foo']
        self.assertEqual(graph['order'], ['entry','other','end'])
        self.assertEqual(graph['edges'], [('entry','end'), ('entry','other'), ('other','end')])
        labels = {(b['from'], b['to']): b['labels'] for b in graph['branches']}
        self.assertEqual(labels[('entry', 'other')], ['true'])
        self.assertEqual(labels[('entry', 'end')], ['false'])
        self.assertEqual(graph['terminals']['end'], ['ret'])

    def test_switch_cases_and_default(self):
        ir = self.root / 'switch.ll'
        ir.write_text(f'''source_filename = "{self.src}"
@pcs = private constant [8 x ptr] [ptr @foo, ptr null, ptr blockaddress(@foo, %one), ptr null, ptr blockaddress(@foo, %two), ptr null, ptr blockaddress(@foo, %otherwise), ptr null], section "__sancov_pcs"
define i32 @foo(i32 %x) !dbg !1 {{
  switch i32 %x, label %otherwise [
    i32 1, label %one
    i32 2, label %two
  ], !dbg !11
one:
  ret i32 1, !dbg !12
two:
  ret i32 2, !dbg !13
otherwise:
  ret i32 0, !dbg !14
}}
!11 = !DILocation(line: 1, column: 1, scope: !1)
!12 = !DILocation(line: 2, column: 1, scope: !1)
!13 = !DILocation(line: 3, column: 1, scope: !1)
!14 = !DILocation(line: 4, column: 1, scope: !1)
''')
        graph = parse_ir(ir)['foo']
        edges = {(b['from'], b['to']): b['labels'] for b in graph['branches']}
        self.assertEqual(edges[('entry','one')], ['case 1'])
        self.assertEqual(edges[('entry','two')], ['case 2'])
        self.assertEqual(edges[('entry','otherwise')], ['default'])

    def test_collapse_only_linear_chains(self):
        graph = {'nodes':[{'name':n, 'line':1, 'pc':'pc', 'hit':True, 'verified':True}
                          for n in ['A','B','C','D','E','F']],
                 'edges':[('A','B'),('B','C'),('C','D'),('C','E'),('D','F'),('E','F')]}
        self.assertEqual(collapsed_groups(graph), [['A','B','C'], ['D'], ['E'], ['F']])
        dot = build_dot(graph, collapsed_groups(graph), simple=True)
        self.assertIn('start -> g0', dot)
        self.assertIn('g0 -> g1', dot)
        self.assertIn('g0 -> g2', dot)
        self.assertIn('g3 -> finish', dot)

    def test_loop_edge_keeps_direction(self):
        graph = {'nodes':[{'name':n,'line':1, 'pc':'p', 'hit':True, 'verified':True}
                          for n in ['A','B','C']],
                 'edges':[('A','B'),('B','A'),('B','C')], 'terminals':{'C':['ret']}}
        dot = build_dot(graph, [[n['name']] for n in graph['nodes']], simple=False)
        self.assertIn('style=dashed', dot)
        self.assertIn('constraint=false', dot)
        self.assertIn('finish', dot)

    def test_runtime_pc_names_match_source_marker_ordinals(self):
        src = str(self.src)
        ir = self.root / 'attach.ll'
        ir.write_text(f'''source_filename = "{src}"
@pcs = private constant [4 x ptr] [ptr @foo, ptr null, ptr blockaddress(@foo, %done), ptr null], section "__sancov_pcs"
define i32 @foo(i32 %x) !dbg !1 {{
 br label %done, !dbg !11
done:
 ret i32 0, !dbg !12
}}
!11 = !DILocation(line: 1, column: 1, scope: !1)
!12 = !DILocation(line: 2, column: 1, scope: !1)
''')
        report = {'files': {src: {'blocks': [
            {'id':'bin@0x11','line':2,'hit':False, 'function':'foo','slot':1},
            {'id':'bin@0x12','line':1,'hit':True,'function':'foo','slot':0}]}}}
        attach_cfg(report,[ir])
        nodes = report['cfg'][0]['nodes']
        self.assertEqual([n['display_id'] for n in nodes], ['BB1','BB2'])
        self.assertEqual([n['hit'] for n in nodes], [True,False])

    def test_llvm_details_are_escaped_and_two_views_exist(self):
        source_page = self.root / 'source.c.gcov.html'
        graph = {'source': str(self.src), 'function':'f',
                 'nodes':[{'name':'entry', 'line':1, 'pc':'binary@0x42', 'hit':True,
                           'verified':True, 'display_id':'BB8', 'source_text':'if (x < 4)',
                           'condition_text':'if (x < 4)', 'terminator':'br i1 %cmp, label %yes, label %no'}],
                 'edges':[], 'terminals':{'entry':['ret']}}
        dest = self.root / 'out.html'
        render_one(graph,dest,source_page)
        html = dest.read_text()
        self.assertIn('data-graph="simple"',html)
        self.assertIn('data-graph="full" hidden',html)
        self.assertIn('ENTRY',html)
        self.assertIn('EXIT',html)
        self.assertIn('if (x &lt; 4)',html)
        self.assertIn('id="node-BB8"',html)
        self.assertIn('binary@0x42',html)
        self.assertNotIn('<?xml version=',html)
        self.assertNotIn('<!DOCTYPE svg',html)


class AttributionTests(unittest.TestCase):
    def report(self):
        return {'schema_version':1,'files':{'a.c':{'covered':1,'total':2,'blocks':[
            {'id':'b@0x1','line':1,'hit':True},{'id':'b@0x2','line':2,'hit':False}]}},
            'summary':{'covered':1,'total':2}, 'unresolved':['b@0x3'],
            'outside_lcov':[{'id':'b@0x4','source':'other.c'}],
            'instrumentation':{'total':4,'covered':2,'mapped_total':2,'mapped_covered':1,
                               'unresolved':1,'outside_lcov':1,'excluded_covered':1}}

    def test_all_raw_pcs_accounted_for(self):
        verify(self.report())
        with self.assertRaisesRegex(AssertionError, 'Strict source attribution'):
            verify(self.report(),strict=True)

    def test_missing_pc_is_rejected(self):
        bad = self.report()
        bad['instrumentation']['total'] = 5
        with self.assertRaisesRegex(AssertionError, 'unaccounted'):
            verify(bad)

    def test_mapping_requiring_no_diagnostics(self):
        ok = self.report()
        ok['unresolved'] = []
        ok['outside_lcov'] = []
        ok['instrumentation'] = {'total':2,'covered':1,'mapped_total':2,'mapped_covered':1,
                                 'unresolved':0,'outside_lcov':0,'excluded_covered':0}
        verify(ok,strict=True)

if __name__ == '__main__':
    unittest.main()
