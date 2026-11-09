"""Build a reproducible, allowlisted submission including new student tests."""
from pathlib import Path
import argparse
import difflib
import hashlib
import io
import json
import re
import tarfile

ROOT=Path(__file__).resolve().parents[1]
MEMO_WORD_LIMIT=500
# (heading, guidance) for each required section of submission/report.md, in order.
REPORT_SECTIONS=[
    ('## 1. Attack walkthrough',
     'Starting state, attacker-controlled input, numbered steps, and the observed effect. '
     'Cite trace files and event numbers.'),
    ('## 2. Security memo (at most 500 words)',
     'The security property, the control you implemented, before/after evidence, the cost to '
     'legitimate use, and a remaining limitation. Answer the memo questions in your handout.'),
    ('## 3. Reproduction',
     'Baseline code revision, exact commands, model ID, endpoint, temperature and other model '
     'settings, repetitions, and Python version. Disclose borrowed code and coding assistance. '
     'Never include an API key: write "set OPENAI_API_KEY" instead.'),
]


def report_template(assignment):
    """The empty report written into every student package."""
    parts=[f'# Assignment {assignment} report\n']
    for heading,guidance in REPORT_SECTIONS:
        parts.append(f'{heading}\n\n<!-- {guidance} -->\n')
    return '\n'.join(parts)


def report_problems(text):
    """Return a list of problems with a filled-in report; empty if it can be submitted."""
    text=re.sub(r'<!--.*?-->','',text,flags=re.S)
    positions=[text.find(heading) for heading,_ in REPORT_SECTIONS]
    if -1 in positions:
        missing=[h for (h,_),pos in zip(REPORT_SECTIONS,positions) if pos==-1]
        return ['missing heading '+repr(h) for h in missing]
    if positions!=sorted(positions):
        return ['keep the section headings in their original order']
    problems=[]
    ends=positions[1:]+[len(text)]
    for (heading,_),start,end in zip(REPORT_SECTIONS,positions,ends):
        body=text[start+len(heading):end]
        if not body.strip():
            problems.append('empty section '+repr(heading))
        if heading.startswith('## 2.') and len(body.split())>MEMO_WORD_LIMIT:
            problems.append(f'the security memo has {len(body.split())} words; the limit is {MEMO_WORD_LIMIT}')
    return problems


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--results',type=Path,required=True,help='Batch directory printed by labagent eval')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    config=json.loads((ROOT/'course.json').read_text())
    if not config['student']: p.error('Run the packager in an exported student bundle')
    manifest=json.loads((ROOT/'.starter/manifest.json').read_text())
    for relative,expected in manifest.items():
        f=ROOT/relative
        if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
            p.error('Trusted scaffold changed: '+relative)
    entries={}
    patches=[]
    for relative in config['editable']:
        file=ROOT/relative
        if file.is_symlink() or not file.is_file(): p.error('Missing or symlinked implementation: '+relative)
        old=(ROOT/'.starter'/relative).read_text().splitlines(keepends=True)
        new=file.read_text().splitlines(keepends=True)
        patches.extend(difflib.unified_diff(old,new,fromfile='a/'+relative,tofile='b/'+relative))
        entries['source/'+relative]=file.read_bytes()
    additions=list((ROOT/'tests/public').glob('test_student*.py'))+list((ROOT/'attacks').glob('*.json'))
    for file in additions:
        if file.is_symlink(): p.error('Symlinks are not accepted')
        rel=str(file.relative_to(ROOT))
        patches.extend(difflib.unified_diff([],file.read_text().splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+rel))
        entries['source/'+rel]=file.read_bytes()
    entries['patch.diff']=''.join(patches).encode()
    report=ROOT/'submission'/'report.md'
    if not report.is_file() or report.is_symlink(): p.error('Missing submission/report.md')
    problems=report_problems(report.read_text())
    if problems: p.error('submission/report.md: '+'; '.join(problems))
    entries['report.md']=report.read_bytes()
    for name in ['results.jsonl','summary.csv']:
        file=args.results/name
        if not file.is_file() or file.is_symlink(): p.error('Missing '+str(file))
        entries[name]=file.read_bytes()
    # Include JSON evidence only. Never copy environment files, SQLite databases,
    # arbitrary directories, or credentials into an archive.
    for file in args.results.rglob('*.json'):
        if file.name=='result.json' or file.name.startswith('session-'):
            if file.is_symlink(): p.error('Symlinked evidence is not accepted')
            entries['traces/'+str(file.relative_to(args.results))]=file.read_bytes()
    entries['submission-manifest.json']=json.dumps({'assignment':config['assignment'],'version':config['version'],
        'files':{k:hashlib.sha256(v).hexdigest() for k,v in entries.items()}},indent=2).encode()
    output=args.output or ROOT/'submission'/f'hw{config["assignment"]}.tar.gz'
    output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(output,'w:gz') as tar:
        for name,data in sorted(entries.items()):
            info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    print(output)


if __name__=='__main__': main()
