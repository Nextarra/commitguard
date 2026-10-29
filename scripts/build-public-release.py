"""Create a reviewed source staging tree; never include private runtime evidence."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

root=Path(__file__).resolve().parent.parent
out=Path(sys.argv[1]).resolve()
if out.exists():raise SystemExit('Use a new destination; existing files are never replaced.')
files=[root/n for n in ['README.md','LICENSE','.gitignore','.env.example','package.json','package-lock.json']]
for folder in ['commitguard','web','tests']:
    files.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.js','.css','.html'} and '__pycache__' not in p.parts and p.name!='test_combined_harness.py')
files.extend(root/'scripts'/n for n in ['run-tests.py','browser-qa.cjs','browser-response-fault.py','build-public-release.py'])
files.extend(root/'docs'/n for n in ['ARCHITECTURE-SECURITY.md','DEMO-STORYBOARD.md','JUDGE-RUNBOOK.md','LIVE-VERIFICATION.md','REQUIREMENTS-TRACEABILITY.md','SUBMISSION-DRAFT.md','TECHNICAL-SOURCES.md'])
files.extend(root/'evidence'/n for n in ['lenovo-http-response-loss.json','lenovo-model-validation.json','lenovo-sandbox-validation.json','lenovo-combined-validation.json','VERIFIED-STATUS.md'])
secret=re.compile(r'sk-(?:proj-)?[A-Za-z0-9_-]{25,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
for path in files:
    if path.is_symlink() or not path.is_file():raise SystemExit('Missing or unsafe allowlisted path: '+path.name)
    if secret.search(path.read_text(encoding='utf-8')):raise SystemExit('Potential secret found; export stopped: '+path.name)
out.mkdir(parents=True)
for path in files:
    target=out/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
metadata={'project':'CommitGuard','license':'MIT','runtime':'Python 3.11+; tested 3.12.14','verification':'Real model proposal and clarification; real sandbox completed capture; combined real model plus sandbox with deliberately discarded capture response recovered by original-order GET','external_real_money':False}
(out/'BUILD-INFO.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'RELEASE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'destination':str(out),'files':len(manifest)+1,'secret_pattern_scan':'passed','runtime_data':'excluded by allowlist'}))
