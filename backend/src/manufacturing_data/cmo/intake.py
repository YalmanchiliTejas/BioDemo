"""Turn whatever a CMO sent into delivery files.

Real deliveries are dumps: ZIPs inside ZIPs, the same file sent twice, cover notes,
operating-system clutter, two different files that share a name. Intake sorts them
instead of refusing the whole upload, and never drops anything silently: every file
ends with exactly one outcome that is shown with the delivery.

Outcomes
  added       stored and read by the delivery checks
  renamed     a different file already had this name; both kept, possible revision
  duplicate   byte-identical to a file already in the delivery; not stored twice
  set_aside   not a data format the checks read (kept as evidence, not read)
  unreadable  an encrypted or corrupt archive that could not be opened (kept as evidence)
  system      operating-system clutter (.DS_Store, __MACOSX, Thumbs.db, Office lock files)
  blocked     an executable or script; listed but its bytes are never stored

Emails (.eml, Outlook .msg) open like folders: the original is kept as evidence, the message
text becomes a readable message.txt, and each attachment goes through the same rules.

Unsafe archives (path traversal, symbolic links, expansion bombs) still reject the upload.
"""
import hashlib
import io
from pathlib import PurePosixPath
import zipfile

from . import mail

SYSTEM_NAMES = {'.ds_store', 'thumbs.db', 'desktop.ini'}
BLOCKED = {'.exe', '.dll', '.com', '.scr', '.msi', '.bat', '.cmd', '.ps1', '.vbs', '.js', '.jar', '.sh', '.app', '.dmg', '.lnk'}
MAX_DEPTH = 4
MAX_MEMBERS = 2000
MAX_EXPANDED = 256 * 1024 * 1024


def _system(path):
    return (any(p == '__MACOSX' for p in path.parts) or path.name.lower() in SYSTEM_NAMES
            or path.name.startswith(('~$', '._')))


def _safe(name):
    path = PurePosixPath(name.replace('\\', '/'))
    if not name or name.startswith('/') or '..' in path.parts or (path.parts and path.parts[0].endswith(':')):
        raise ValueError(f'Unsafe file path in upload: {name}')
    return path


def expand(filename, data, allowed):
    """[(path, bytes, outcome, reason)] for one uploaded file; nested ZIPs unpack into a folder named after them."""
    out, budget = [], {'members': 0, 'bytes': 0}

    def visit(path, content, depth):
        if _system(path):
            out.append((path, content, 'system', 'operating-system file'))
        elif path.suffix.lower() in BLOCKED:
            out.append((path, content, 'blocked', 'executable or script: not stored'))
        elif path.suffix.lower() == '.zip':
            if depth >= MAX_DEPTH:
                out.append((path, content, 'unreadable', f'ZIP nested more than {MAX_DEPTH} levels deep'))
                return
            try:
                archive = zipfile.ZipFile(io.BytesIO(content))
                members = [m for m in archive.infolist() if not m.is_dir()]
            except zipfile.BadZipFile:
                out.append((path, content, 'unreadable', 'not a readable ZIP archive'))
                return
            # An uploaded archive unpacks where it was dropped; nested archives get their own folder.
            base = path.parent if depth == 0 else path.with_suffix('')
            for member in members:
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f'Linked ZIP member rejected: {member.filename}')
                budget['members'] += 1
                budget['bytes'] += member.file_size
                if budget['members'] > MAX_MEMBERS or budget['bytes'] > MAX_EXPANDED:
                    raise ValueError('Upload expands beyond the delivery limits')
                inner = base / _safe(member.filename)
                if member.flag_bits & 1:
                    out.append((inner, b'', 'unreadable', 'encrypted ZIP member'))
                    continue
                visit(inner, archive.read(member), depth + 1)
        elif path.suffix.lower() in ('.eml', '.msg'):
            if depth >= MAX_DEPTH:
                out.append((path, content, 'unreadable', f'email nested more than {MAX_DEPTH} levels deep'))
                return
            try:
                text, attachments = mail.read(path.suffix.lower(), content)
            except Exception as exc:  # any malformed email is reported, never fatal to the upload
                out.append((path, content, 'unreadable', f'email could not be opened ({type(exc).__name__})'))
                return
            folder = path.with_suffix('')
            out.append((path, content, 'set_aside', f'original email kept; its text and attachments are in {folder.as_posix()}/'))
            out.append((folder / 'message.txt', text.encode(), 'added', 'text of the email'))
            for name, body, kind in attachments:
                budget['members'] += 1
                budget['bytes'] += len(body)
                if budget['members'] > MAX_MEMBERS or budget['bytes'] > MAX_EXPANDED:
                    raise ValueError('Upload expands beyond the delivery limits')
                inner = folder / (PurePosixPath(name.replace('\\', '/')).name or 'attachment')
                if kind == 'inline':
                    out.append((inner, body, 'system', 'image embedded in the email body (logo or signature)'))
                elif kind == 'embedded':
                    out.append((inner, body, 'unreadable', 'attached Outlook item: open it in Outlook and save it as a file'))
                else:
                    visit(inner, body, depth + 1)
        elif path.suffix.lower() in allowed:
            out.append((path, content, 'added', ''))
        else:
            out.append((path, content, 'set_aside', f'{path.suffix or "no extension"} is not a data format the checks read'))

    visit(_safe(filename), data, 0)  # filename may carry the folder path of a dropped directory
    return out


NARRATIVE = {'.txt', '.log', '.pdf', '.docx'}
MAX_TEXT = 200_000


def document_text(path):
    """Readable text of a narrative file, or None for data files (tables become measurements instead)."""
    suffix = path.suffix.lower()
    if suffix not in NARRATIVE:
        return None
    try:
        if suffix == '.pdf':
            from pypdf import PdfReader
            text = '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
        elif suffix == '.docx':
            from docx import Document
            text = '\n'.join(p.text for p in Document(str(path)).paragraphs)
        else:
            text = path.read_bytes().decode('utf-8', errors='replace')
    except Exception as exc:  # an unreadable document is reported, not fatal
        return f'[text could not be extracted: {type(exc).__name__}]'
    # ponytail: fixed cap; page through originals if assistants need longer reports.
    return text[:MAX_TEXT] + ('\n[truncated]' if len(text) > MAX_TEXT else '')


def reconcile(entries, existing):
    """Decide duplicates and name clashes against files already in the delivery.

    existing: {path: sha256}. Returns entries with final paths and outcomes, plus sha256.
    """
    by_sha = {sha: path for path, sha in existing.items()}
    taken = set(existing)
    result = []
    for path, content, outcome, reason in entries:
        sha = hashlib.sha256(content).hexdigest()
        rel = path.as_posix()
        if outcome == 'added':
            if sha in by_sha:
                outcome, reason = 'duplicate', f'identical to {by_sha[sha]}'
            elif rel in taken:
                stem, n = path.with_suffix(''), 2
                while (candidate := f'{stem} ({n}){path.suffix}') in taken:
                    n += 1
                outcome, reason = 'renamed', f'{rel} already exists with different content; check whether this replaces it'
                rel = candidate
            elif clash := next((t for t in taken if PurePosixPath(t).name == path.name), None):
                reason = f'same file name as {clash} with different content; possibly a revision'
            if outcome in ('added', 'renamed'):
                by_sha[sha] = rel
                taken.add(rel)
        result.append({'path': rel, 'content': content, 'outcome': outcome, 'reason': reason, 'sha256': sha})
    return result


if __name__ == '__main__':
    def zipped(files):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            for name, body in files.items():
                z.writestr(name, body)
        return buffer.getvalue()
    inner = zipped({'lims.csv': b'a,b\n1,2', 'notes.md': b'# hi'})
    dump = zipped({'lims.csv': b'a,b\n1,2', 'month/inner.zip': inner, '__MACOSX/._x': b'', 'trend.csv': b'x\n1',
                   'again/trend.csv': b'x\n9', 'tool.exe': b'MZ'})
    got = {e['path']: e['outcome'] for e in reconcile(expand('dump.zip', dump, {'.csv'}), {'trend.csv': 'other'})}
    assert got == {'lims.csv': 'added', 'month/inner/lims.csv': 'duplicate', 'month/inner/notes.md': 'set_aside',
                   '__MACOSX/._x': 'system', 'trend (2).csv': 'renamed', 'again/trend.csv': 'added',
                   'tool.exe': 'blocked'}, got
    from email.message import EmailMessage
    note = EmailMessage(); note['From'] = 'qa@cmo.example'; note['Subject'] = 'Batch 17 failed titer'
    note.set_content('Batch 17 failed the titer spec, see attached.')
    note.add_attachment(b'a,b\n1,2', maintype='text', subtype='csv', filename='batch17.csv')
    note.add_attachment(zipped({'coa.csv': b'x\n1'}), maintype='application', subtype='zip', filename='coa.zip')
    note.add_attachment(b'\x89PNG', maintype='image', subtype='png', filename='logo.png', disposition='inline')
    got = {p.as_posix(): o for p, _, o, _ in expand('Re- batch 17.eml', note.as_bytes(), {'.csv', '.txt'})}
    assert got == {'Re- batch 17.eml': 'set_aside', 'Re- batch 17/message.txt': 'added', 'Re- batch 17/batch17.csv': 'added',
                   'Re- batch 17/coa/coa.csv': 'added', 'Re- batch 17/logo.png': 'system'}, got
    assert b'failed the titer spec' in next(c for p, c, _, _ in expand('m.eml', note.as_bytes(), {'.txt'}) if p.name == 'message.txt')
    try:
        expand('bad.zip', zipped({'../evil.csv': b'x'}), {'.csv'})
        raise AssertionError('traversal accepted')
    except ValueError:
        pass
    print('ok')
