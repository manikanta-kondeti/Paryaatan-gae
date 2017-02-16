from collections import namedtuple
import cStringIO

import lib.cloudstorage as gcs

# Constants and module globals
BUCKET_ROOT = '/foss4gasia-challenge.appspot.com'
BUCKET_PATH_SEP = '/'

TypeDescriptor = namedtuple('TypeDescriptor', ['mime_type', 'bucket_path'])
MIME_TYPE_MAP = dict(
    gif=TypeDescriptor(mime_type='image/gif', bucket_path=['poster']),
    jpeg=TypeDescriptor(mime_type='image/jpeg', bucket_path=['poster']),
    jpg=TypeDescriptor(mime_type='image/jpeg', bucket_path=['poster']),
    png=TypeDescriptor(mime_type='image/png', bucket_path=['poster']),
    json=TypeDescriptor(mime_type='application/json', bucket_path=['application']),
    zip=TypeDescriptor(mime_type='application/zip', bucket_path=['application']),
    mp3=TypeDescriptor(mime_type='audio/mpeg', bucket_path=['audio', 'mp3']),
    ogg=TypeDescriptor(mime_type='audio/ogg', bucket_path=['audio', 'opus']),
    opus=TypeDescriptor(mime_type='audio/ogg', bucket_path=['audio', 'opus'])
)


# Module specific functions
class UnknownFiletype(BaseException):
    pass


def _resolve_file_path(filename):
    """Meant for use within the module, returns the full-bucket path for the given file and the mimetype"""
    filetype = filename.rsplit('.', 1)[-1]
    type_description = MIME_TYPE_MAP.get(filetype)
    if not type_description:
        raise UnknownFiletype('Unknown file type: %s, for file: %s' % (filename, filetype))

    path = BUCKET_PATH_SEP.join([BUCKET_ROOT] + type_description.bucket_path + [filename])
    return path, type_description.mime_type


def _gcs_open(filepath, mode, content_type=None, **kwargs):
    """
    Context manager for gcs file opening.
    kwargs are passed along as is.
    MIME type is auto resolved if one not provided.
    """
    if content_type is None:
        extension = filepath.rsplit('.', 1)[-1]
        desc = MIME_TYPE_MAP.get(extension)
        if not desc:
            raise UnknownFiletype('Unknown file type for: %s' % filepath)
        content_type = desc.mime_type
    f = None

    try:
        f = gcs.open(filepath, mode, content_type, **kwargs)
        yield f
    finally:
        if f:
            f.close()


# GCS interface
def put_file(filename, contents):
    """
    Saves the file to google cloud storage

    filename: Name of the file we want to store, including the extension
    contents: file contents as byte string

    The bucket path is auto-resolved based on file type.

    Returns the fullpath and the mime type
    """
    # TODO: Eventually, validate given contents against the given type
    path, mime_type = _resolve_file_path(filename)

    with _gcs_open(path, mode='w', content_type=mime_type) as f:
        f.write(contents)
    return path, mime_type


def get_file(filename):
    """Returns the gcs file contents and the mime type"""
    path, mime_type = _resolve_file_path(filename)
    contents = None
    with _gcs_open(path, mode='r', content_type=mime_type) as f:
        contents = f.read()

    return contents, mime_type

def unicode_to_string(file_contents):
    string_contents = cStringIO.StringIO()
    string_contents.write(file_contents.decode('base64'))
    string_contents.seek(0)
    return string_contents.read()

def store_image_file(filename, file_contents):
    write_retry_params = gcs.RetryParams(backoff_factor=1.1)
    gcs_file = gcs.open(filename,
                          'w',
                          content_type='image/jpeg',
                          retry_params=write_retry_params)
    gcs_file.write(file_contents)
    gcs_file.close()
    return

# External facing helpers