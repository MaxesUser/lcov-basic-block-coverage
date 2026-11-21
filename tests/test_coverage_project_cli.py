"""Tests for the generic source-file coverage CLI (without compiler dependency)."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace

path = Path(__file__).resolve().parents[1] / 'scripts' / 'coverage_project.py'
spec = importlib.util.spec_from_file_location('coverage_project', path)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class GenericProjectTests(TestCase):
    def test_project_name_rejects_path_traversal(self):
        for name in ('../escape', '/tmp/a', 'dir/sub', '', '..', '-x'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                cli.project_dir(name)

    def test_project_name_isolation(self):
        p = cli.project_dir('foo-bar_1')
        self.assertEqual(p, cli.ROOT / 'build' / 'projects' / 'foo-bar_1')

    def test_run_passes_arguments_and_both_profile_directories(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / 'build' / 'projects' / 'sample' / 'program'
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.object(cli, 'ROOT', root), \
                 patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
                cli.run_project(SimpleNamespace(name='sample', args=['--', '--flag', 'a b'], allow_nonzero=False))
            self.assertEqual(run.call_args.args[0], [str(exe), '--flag', 'a b'])
            env = run.call_args.kwargs['env']
            self.assertEqual(env['BBRAW_DIR'], str(exe.parent / 'raw'))
            self.assertEqual(env['LLVM_PROFILE_FILE'], str(exe.parent / 'profiles' / '%p.profraw'))

    def test_nonzero_exit_requires_opt_in(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            exe = root / 'build' / 'projects' / 'sample' / 'program'
            exe.parent.mkdir(parents=True)
            exe.touch()
            args = SimpleNamespace(name='sample', args=[], allow_nonzero=False)
            with patch.object(cli, 'ROOT', root), \
                 patch.object(cli.subprocess, 'run', return_value=SimpleNamespace(returncode=2)):
                with self.assertRaisesRegex(RuntimeError, 'Program exited with 2'):
                    cli.run_project(args)
                args.allow_nonzero = True
                cli.run_project(args)

    def test_build_requires_source(self):
        args = SimpleNamespace(name='test', source=[], include=[], llvm_version='19',
                               cflag=[], ldflag=[], force=False)
        with self.assertRaisesRegex(ValueError, 'At least one --source'):
            cli.compile_project(args)
