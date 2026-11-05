"""Build a reproducible, allowlisted submission including new student tests."""
from pathlib import Path
import argparse
import difflib
import hashlib
import io
import json
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--results',type=Path,required=True,help='Batch directory printed by lab eval')
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    config=json.loads((ROOT/'course.json').read_text())
    if not config['student']: p.error('Run the packager in an exported student snapshot')
    manifest=json.loads((ROOT/'.starter/manifest.json').read_text())
    for relative,expected in manifest.items():
        f=ROOT/relative
        if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
            p.error('Trusted scaffold changed: '+relative)
    entries={}
    patches=[]
    for relative in config['editable']:
        file=ROOT/relative
        if file.is_symlink() or not file.is_file(): p.error('Missing or symlinked hook: '+relative)
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
    for name in ['memo.md','exploit.md','README.md']:
        file=ROOT/'submission'/name
        if not file.is_file() or file.is_symlink(): p.error('Missing submission/'+name)
        entries[name]=file.read_bytes()
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
