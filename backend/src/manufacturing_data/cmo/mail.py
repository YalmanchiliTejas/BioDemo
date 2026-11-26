"""Read an email a CMO sent (.eml or Outlook .msg) into its text and its attachments.

The cover email is often where the important part is ("batch 17 failed the titer spec,
see attached"), so its text is kept as a readable file, not discarded.
"""
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
import html
import io
import re
import struct


def read(suffix, content):
    """(message_text, [(filename, bytes, kind)]) where kind is 'file', 'inline' or 'embedded'."""
    return _msg(content) if suffix == '.msg' else _eml(content)


def _text(headers, body):
    lines = [f'{k}: {v}' for k, v in headers if v]
    return '\n'.join(lines) + '\n\n' + body.strip() + '\n'


def _strip_html(markup):
    markup = re.sub(r'(?is)<(script|style).*?</\1>', ' ', markup)
    markup = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</tr>', '\n', markup)
    return html.unescape(re.sub(r'<[^>]+>', ' ', markup))


def _eml(content):
    message = BytesParser(policy=policy.default).parsebytes(content)
    body = message.get_body(preferencelist=('plain', 'html'))
    text = body.get_content() if body else ''
    if body is not None and body.get_content_type() == 'text/html':
        text = _strip_html(text)
    parts = []
    for i, part in enumerate(message.iter_attachments(), 1):
        name = part.get_filename()
        if part.get_content_type() == 'message/rfc822':  # a forwarded email
            data = part.get_payload(0).as_bytes() if part.is_multipart() else part.get_payload(decode=True) or b''
            name = name if name and name.lower().endswith('.eml') else f'{name or f"forwarded-{i}"}.eml'
        else:
            data = part.get_payload(decode=True) or b''
        inline = part.get_content_disposition() == 'inline' and part.get_content_maintype() == 'image'
        parts.append((name or f'attachment-{i}', data, 'inline' if inline else 'file'))
    headers = [(h, message.get(h)) for h in ('From', 'To', 'Cc', 'Date', 'Subject')]
    return _text(headers, text), parts


# Outlook .msg is an OLE compound file of MAPI property streams.
_STRING = (('001F', 'utf-16-le'), ('001E', 'cp1252'))


def _msg(content):
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(content))

    def prop(storage, tag):
        for kind, encoding in _STRING:
            name = f'{storage}__substg1.0_{tag}{kind}'
            if ole.exists(name):
                return ole.openstream(name).read().decode(encoding, errors='replace').rstrip('\x00')
        return ''

    def sent():  # PR_CLIENT_SUBMIT_TIME (0x0039, PT_SYSTIME) in the top-level property stream
        if not ole.exists('__properties_version1.0'):
            return ''
        raw = ole.openstream('__properties_version1.0').read()
        for offset in range(32, len(raw) - 15, 16):
            ptype, pid = struct.unpack_from('<HH', raw, offset)
            if pid == 0x0039 and ptype == 0x0040:
                ticks = struct.unpack_from('<Q', raw, offset + 8)[0]
                return (datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)).isoformat()
        return ''

    body = prop('', '1000') or _strip_html(prop('', '1013'))
    headers = [('From', ' '.join(filter(None, [prop('', '0C1A'), f"<{prop('', '0C1F')}>" if prop('', '0C1F') else '']))),
               ('To', prop('', '0E04')), ('Cc', prop('', '0E03')), ('Date', sent()), ('Subject', prop('', '0037'))]
    parts = []
    storages = sorted({e[0] for e in ole.listdir(streams=True, storages=True) if e[0].startswith('__attach_version1.0_')})
    for i, storage in enumerate(storages, 1):
        root = f'{storage}/'
        name = prop(root, '3707') or prop(root, '3704') or f'attachment-{i}'
        if ole.exists(f'{root}__substg1.0_37010102'):
            data = ole.openstream(f'{root}__substg1.0_37010102').read()
            inline = bool(prop(root, '3712')) and prop(root, '370E').startswith('image/')
            parts.append((name, data, 'inline' if inline else 'file'))
        else:  # an attached Outlook item is stored as a sub-storage, not bytes
            parts.append((name, b'', 'embedded'))
    return _text(headers, body), parts
