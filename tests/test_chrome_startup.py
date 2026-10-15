"""Browser readiness and startup failures must report Chrome's actual state."""
import json
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).with_name("chrome_startup.mjs").as_uri()


@pytest.mark.parametrize("child, timeout, expected, succeeds", [
    (
        'process.stderr.write("DevTools listening on ws://127.0.0.1:1234/devtools/brow");'
        'setTimeout(() => process.stderr.write("ser/test\\n"), 50);setInterval(() => {}, 1000);',
        2000, "ws://127.0.0.1:1234/devtools/browser/test", True,
    ),
    ('process.stderr.write("profile cannot be opened\\n");process.exit(23);',
     2000, "profile cannot be opened", False),
    ('setInterval(() => {}, 1000);', 100, "did not announce DevTools within 100ms", False),
])
def test_browser_readiness_and_failures(child, timeout, expected, succeeds):
    script = f"""
        import {{ spawn }} from 'node:child_process';
        import {{ waitForDevTools }} from {json.dumps(HELPER)};
        const proc = spawn(process.execPath, ['-e', {json.dumps(child)}], {{stdio: ['ignore', 'ignore', 'pipe']}});
        try {{ console.log(await waitForDevTools(proc, {timeout})); }}
        catch (error) {{ console.error(error.message); process.exitCode = 1; }}
        finally {{ proc.kill('SIGKILL'); }}
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True, text=True, timeout=5,
    )
    assert (proc.returncode == 0) is succeeds, proc.stderr
    assert expected in proc.stdout + proc.stderr
    if succeeds:
        assert proc.stdout.strip() == expected
    elif "profile" in expected:
        assert "code 23" in proc.stderr
