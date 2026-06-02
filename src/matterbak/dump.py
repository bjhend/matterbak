"""
Provide functions to dump data into JSON files
"""


import datetime
import json
import signal

from .ignoresignals import IgnoreSignals


# Separator between parts of a filename
filename_separator = '__'
# Format for timestamps in file names
timestamp_format = "%Y%m%d-%H%M%S%f"


def make_filename(id_, name=None, extension='', mm_timestamp=None):
    """Make a filename for a backup file

    id_:          Mattermost ID to insert into the filename
    name:         optional name to append
    extension:    optional extension for the filename
    mm_timestamp: optional Mattermost timestamp (Unix time in milliseconds)

    return: filename
    """
    filename_parts = []
    if mm_timestamp:
        now = datetime.datetime.fromtimestamp(mm_timestamp / 1000)
        filename_parts.append(now.strftime(timestamp_format))
    filename_parts.append(id_)
    if name:
        filename_parts.append(name)

    return filename_separator.join(filename_parts) + extension


def dump_image(dir, id_, image_loader, label=None, skip_existing=False):
    """Helper to download and save an image from Mattermost

    Calls make_filename with id_, label as name, and extension derived from the
    content type returned from Mattermost.

    dir:           pathlib.Path of the folder to store the image in
    id_:           Mattermost ID as prefix for the filename
    image_loader:  function returning an image Response object from Mattermost API
    label:         label to append to filename
    skip_existing: if True skip download if image file already exists
    """

    found_image_files = [ f for f in dir.glob(id_+'*') if f.suffix != '.json' and f.is_file() ]
    if skip_existing and found_image_files:
        return

    # The new image file may have a different extension so delete all existing
    # image files.
    for image in found_image_files:
        image.unlink(missing_ok=True)

    response = image_loader()
    if not response.ok:
        return

    content_type_prefix = 'image/'
    content_type = response.headers.get('content-type', '')
    if not content_type.startswith(content_type_prefix):
        print(f"Cannot store image of type '{content_type}' for ID {id_}")
        return
    extension = '.' + content_type.removeprefix(content_type_prefix)

    with IgnoreSignals():
        path = dir / make_filename(id_=id_, name=label, extension=extension)
        path.write_bytes(response.content)


def dump_content(dir, content, id_=None, name=None, with_timestamp=False, return_old_content=False):
    """Helper to save the content as JSON file

    Calls make_filename with id_ (if given else content['id']), name, and
    with_timestamp to create the filename.

    dir:                pathlib.Path of the folder to store the file in
    content:            data to store
    id_:                Mattermost ID to be integrated into filename, if None use
                        content['id'] instead
    name:               name (without .json extension) of the file, can be empty
    with_timestamp:     set to True to prefix filename with content's creation time
    return_old_content: if True content of file to be overwritten is returned
                        or None if there was no content file
    """

    if not id_:
        id_ = content['id']
    mm_timestamp = content["create_at"] if with_timestamp else None

    path = dir / make_filename(id_, name=name, extension='.json', mm_timestamp=mm_timestamp)

    old_content = None
    if return_old_content and path.is_file():
        with path.open(encoding="utf8") as old_file:
            old_content = json.load(old_file)

    with IgnoreSignals():
        with path.open(mode="w", encoding="utf8") as dump_file:
            json.dump(content, dump_file)

    return old_content

