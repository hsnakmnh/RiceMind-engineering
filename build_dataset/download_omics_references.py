#!/usr/bin/env python3
"""Download official RiceMind references (Ensembl Plants 59), Python 3.8+ stdlib.
Preserve Oryzabase's server filename/encoding; create a separate UTF-8 copy.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://ftp.ebi.ac.uk/ensemblgenomes/pub/plants/release-59'
ORYZA_URL = 'https://shigen.nig.ac.jp/rice/oryzabase/gene/download?classtag=GENE_EN_LIST'
SOURCES = {
    'gff3': ('Oryza_sativa.IRGSP-1.0.59.gff3.gz', 'gff3/oryza_sativa'),
    'dna': ('Oryza_sativa.IRGSP-1.0.dna.toplevel.fa.gz', 'fasta/oryza_sativa/dna'),
    'cdna': ('Oryza_sativa.IRGSP-1.0.cdna.all.fa.gz', 'fasta/oryza_sativa/cdna'),
    'pep': ('Oryza_sativa.IRGSP-1.0.pep.all.fa.gz', 'fasta/oryza_sativa/pep'),
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def write_manifest(path, data):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)

def request(url, method='GET', headers=None):
    merged = {'User-Agent': 'RiceMind-reference-downloader/1.0', 'Accept-Encoding': 'identity'}
    merged.update(headers or {})
    return urlopen(Request(url, method=method, headers=merged), timeout=90)

def download(url, path, headers):
    length = headers.get('Content-Length')
    expected = int(length) if length and length.isdigit() else None
    if path.exists():
        if expected is not None and path.stat().st_size != expected:
            raise ValueError('Existing file size mismatch: ' + str(path))
        print('[REUSE] ' + path.name, flush=True)
        return
    part = path.with_name(path.name + '.part')
    for attempt in range(1, 5):
        offset = part.stat().st_size if part.exists() else 0
        if expected and offset == expected:
            part.replace(path)
            return
        extra = {'Range': 'bytes={}-'.format(offset)} if offset else {}
        if offset and (headers.get('ETag') or headers.get('Last-Modified')):
            extra['If-Range'] = headers.get('ETag') or headers['Last-Modified']
        try:
            with request(url, headers=extra) as response:
                append = response.status == 206
                if append and not response.headers.get('Content-Range', '').startswith('bytes {}-'.format(offset)):
                    raise ValueError('Incorrect range response')
                if not append:
                    offset = 0
                size = offset
                content_length = response.headers.get('Content-Length')
                response_size = int(content_length) if content_length and content_length.isdigit() else None
                next_log = time.monotonic() + 15
                print('[DOWNLOAD] {} (resume={} bytes)'.format(path.name, offset), flush=True)
                with part.open('ab' if append else 'wb') as f:
                    for chunk in iter(lambda: response.read(512 * 1024), b''):
                        f.write(chunk)
                        size += len(chunk)
                        if time.monotonic() >= next_log:
                            print('[PROGRESS] {}: {:.1f} MiB{}'.format(path.name, size / 1048576,
                                  ' / {:.1f} MiB'.format(expected / 1048576) if expected else ''), flush=True)
                            next_log = time.monotonic() + 15
                if response_size is not None and size - offset != response_size:
                    raise OSError('Incomplete HTTP response')
                if expected is not None and size != expected:
                    raise OSError('HTTP Content-Length mismatch')
                if size == 0:
                    raise OSError('Empty download')
            part.replace(path)
            print('[DONE] {}: {:,} bytes'.format(path.name, size), flush=True)
            return
        except OSError as error:
            if attempt == 4:
                raise
            print('[RETRY] {} {}: {}'.format(attempt, path.name, error), flush=True)
            time.sleep(min(2 * attempt, 10))

def record(path, url, headers):
    return dict(filename=path.name, source_url=url, size_bytes=path.stat().st_size,
                sha256=digest(path), etag=headers.get('ETag'), last_modified=headers.get('Last-Modified'),
                downloaded_at_utc=utc_now())

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir', type=Path, default=ROOT / 'sequence_data' / 'reference')
    args = p.parse_args()
    folder = args.data_dir.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'reference_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else dict(
        ensembl_release=59, assembly='IRGSP-1.0', files={}, status='incomplete',
        notes=['Current official Oryzabase snapshot, not the author\'s 2025-07-02 export.',
               'Local SHA-256, HTTP length checks and full gzip CRC validation.'])
    if manifest.get('ensembl_release') != 59:
        raise ValueError('Manifest is for a different release')
    prior = manifest['files'].get('oryzabase_raw')
    if prior and (folder / prior['filename']).is_file():
        raw = folder / prior['filename']
        if digest(raw) != prior['sha256']:
            raise ValueError('Oryzabase snapshot hash changed')
        print('[REUSE] ' + raw.name, flush=True)
    else:
        with request(ORYZA_URL, 'HEAD') as r:
            headers = r.headers
        m = re.search(r'filename="?(OryzabaseGeneListEn_\d+\.txt)"?', headers.get('Content-Disposition', ''))
        if not m:
            raise ValueError('Official response has no expected Oryzabase filename')
        raw = folder / m.group(1)
        download(ORYZA_URL, raw, headers)
        manifest['files']['oryzabase_raw'] = record(raw, ORYZA_URL, headers)
    content = raw.read_bytes()
    try:
        text, encoding = content.decode('utf-8-sig'), 'utf-8-sig'
    except UnicodeDecodeError:
        text, encoding = content.decode('cp932'), 'cp932'
    rows = csv.reader(io.StringIO(text), delimiter='\t')
    columns = [x.strip() for x in next(rows)]
    if not {'CGSNL Gene Symbol', 'RAP ID', 'MSU ID'} <= set(columns):
        raise ValueError('Unexpected Oryzabase columns: ' + repr(columns))
    count = sum(1 for row in rows if any(row))
    if not count:
        raise ValueError('Oryzabase export has no rows')
    normalized = raw.with_name(raw.stem + '.utf8.tsv')
    payload = text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    if normalized.exists() and normalized.read_bytes() != payload:
        raise ValueError('Refusing to overwrite a different normalized copy')
    normalized.write_bytes(payload)
    manifest['files']['oryzabase_raw'].update(encoding=encoding, rows=count)
    manifest['files']['oryzabase_utf8'] = dict(filename=normalized.name, sha256=digest(normalized),
        size_bytes=normalized.stat().st_size, encoding='utf-8', rows=count, columns=columns, derived_from=raw.name)
    write_manifest(manifest_path, manifest)
    for role, (filename, directory) in SOURCES.items():
        url, path = BASE + '/' + directory + '/' + filename, folder / filename
        prior = manifest['files'].get(role)
        if prior and path.exists() and digest(path) != prior['sha256']:
            raise ValueError('Reference hash changed: ' + str(path))
        with request(url, 'HEAD') as r:
            headers = r.headers
        download(url, path, headers)
        with gzip.open(path, 'rb') as f:
            for _ in iter(lambda: f.read(1024 * 1024), b''):
                pass
        manifest['files'][role] = record(path, url, headers)
        manifest['files'][role]['gzip_crc_validated'] = True
        write_manifest(manifest_path, manifest)
        print('[VERIFIED] ' + filename, flush=True)
    manifest.update(status='complete', completed_at_utc=utc_now())
    write_manifest(manifest_path, manifest)
    print('[COMPLETE] ' + str(manifest_path), flush=True)

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, UnicodeError, EOFError) as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(2)
