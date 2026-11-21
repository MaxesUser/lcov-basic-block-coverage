import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bb_cfg import parse_ir, attach_cfg
from bb_html import inject


def example_ir(src):
    return f'''source_filename = "{src}"
@__sancov_gen_.1 = private constant [6 x ptr] [ptr @foo, ptr inttoptr (i64 1 to ptr), ptr blockaddress(@foo, %then), ptr null, ptr blockaddress(@foo, %exit), ptr null], section "__sancov_pcs", align 8
define dso_local i32 @foo(i32 %x) #0 !dbg !5 {{
  br i1 true, label %then, label %exit, !dbg !11
then:                         ; preds = %entry
  br label %exit, !dbg !12
exit:                         ; preds = %entry, %then
  ret i32 0, !dbg !13
}}
!11 = !DILocation(line: 1, column: 1, scope: !5)
!12 = !DILocation(line: 2, column: 1, scope: !5)
!13 = !DILocation(line: 3, column: 1, scope: !5)
'''


class CFGTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / 'sample.c'
        self.src.write_text('int foo(int x) {\n  return x;\n}\n')
        self.ir = self.root / 'sample.ll'
        self.ir.write_text(example_ir(self.src))

    def tearDown(self):
        self.tmp.cleanup()

    def report(self, *, mismatch=False):
        blocks = [
            {'id': '/bin/example@0x30', 'slot': 0, 'line': 1, 'hit': True, 'function': 'foo'},
            {'id': '/bin/example@0x10', 'slot': 1, 'line': 50 if mismatch else 2,
             'hit': False, 'function': 'foo'},
            {'id': '/bin/example@0x20', 'slot': 2, 'line': 3, 'hit': True, 'function': 'foo'},
        ]
        return {'schema_version': 1, 'summary': {'covered': 2, 'total': 3},
                'files': {str(self.src): {'covered': 2, 'total': 3, 'blocks': blocks}}}

    def test_parse_instrumented_table_and_edges(self):
        result = parse_ir(self.ir)
        self.assertEqual(result['foo']['order'], ['entry', 'then', 'exit'])
        self.assertEqual(result['foo']['edges'], [('entry', 'exit'), ('entry', 'then'), ('then', 'exit')])

    def test_runtime_slot_not_address_order(self):
        data = attach_cfg(self.report(), [self.ir])
        graph = data['cfg'][0]
        self.assertEqual([n['pc'] for n in graph['nodes']],
                         ['/bin/example@0x30', '/bin/example@0x10', '/bin/example@0x20'])
        self.assertEqual([n['hit'] for n in graph['nodes']], [True, False, True])

    def test_disagreeing_dwarf_line_is_unknown(self):
        data = attach_cfg(self.report(mismatch=True), [self.ir])
        self.assertIsNone(data['cfg'][0]['nodes'][1]['hit'])
        self.assertFalse(data['cfg'][0]['nodes'][1]['verified'])

    def test_html_has_clickable_markers_and_cfg(self):
        data = attach_cfg(self.report(), [self.ir])
        report = self.root / 'bb.json'
        report.write_text(json.dumps(data))
        output = self.root / 'html'
        output.mkdir()
        source_rows = '\n'.join(
            f'<span id="L{i}"><span class="lineNum">{i}</span><span class="lineCov">code</span></span>'
            for i in range(1, 4))
        (output / 'index.html').write_text('<html><body></body></html>')
        page = output / 'sample.c.gcov.html'
        page.write_text(f'<html><body><pre class="source">{source_rows}</pre></body></html>')
        inject(report, output)
        html = page.read_text()
        self.assertIn('id="bb-dialog"', html)
        self.assertEqual(html.count('role="button" tabindex="0"'), 3)
        self.assertIn('data-bb-cfg="bb-cfg/', html)
        graphs = list((output / 'bb-cfg').glob('*.html'))
        self.assertEqual(len(graphs), 1)
        graph_html = graphs[0].read_text()
        self.assertIn('LLVM instrumented CFG', graph_html)
        self.assertIn('<svg', graph_html)
        self.assertIn('<b>Covered:</b> 2', graph_html)
        self.assertIn('<b>Uncovered:</b> 1', graph_html)
        self.assertEqual(len(re.findall('class="node"', graph_html)), 10)  # 2 views, each: ENTRY, EXIT, 3 BBs
        # Repeated injection is idempotent, including linked CFG pages.
        inject(report, output)
        self.assertEqual(html, page.read_text())
        self.assertEqual(len(list((output / 'bb-cfg').glob('*.html'))), 1)


if __name__ == '__main__':
    unittest.main()
