"""
Provide functions to dump data into JSON files
"""


import datetime
import json
import pathlib as pl

from .ignoresignals import IgnoreSignals

JSON_EXTENSION = '.json'
# Separator between parts of a filename
FILENAME_SEPARATOR = '__'
# Format for timestamps in file names
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S%f"

# Subdirs below data_dir to store the related downloads
teams_subdir = pl.Path('teams')
groups_subdir = pl.Path('groups')
direct_subdir = pl.Path('direct')
emojis_subdir = pl.Path('emojis')
users_subdir = pl.Path('users')
files_subdir = pl.Path('files')

# Suffixes for types of data files
SUFFIX_MEMBERS = 'members'
SUFFIX_THREADS = 'threads'
SUFFIX_ICON = 'icon'
SUFFIX_IMAGE = 'image'


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
        filename_parts.append(now.strftime(TIMESTAMP_FORMAT))
    filename_parts.append(id_)
    if name:
        filename_parts.append(name)

    return FILENAME_SEPARATOR.join(filename_parts) + extension


def dump_image(directory, id_, image_loader, label=None, skip_existing=False):
    """Helper to download and save an image from Mattermost

    Calls make_filename with id_, label as name, and extension derived from the
    content type returned from Mattermost.

    directory:     pathlib.Path of the folder to store the image in
    id_:           Mattermost ID as prefix for the filename
    image_loader:  function returning an image Response object from Mattermost API
    label:         label to append to filename
    skip_existing: if True skip download if image file already exists
    """

    found_image_files = [f for f in directory.glob(
        id_+'*') if f.suffix != JSON_EXTENSION and f.is_file()]
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
        path = directory / \
            make_filename(id_=id_, name=label, extension=extension)
        path.write_bytes(response.content)


def dump_content(directory, content, id_=None, name=None, with_timestamp=False,
                 return_old_content=False):
    # pylint: disable = too-many-arguments, too-many-positional-arguments
    """Helper to save the content as JSON file

    Calls make_filename with id_ (if given else content['id']), name, and
    with_timestamp to create the filename.

    directory:          pathlib.Path of the folder to store the file in
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

    path = directory / \
        make_filename(id_, name=name, extension=JSON_EXTENSION,
                      mm_timestamp=mm_timestamp)

    old_content = None
    if return_old_content and path.is_file():
        with path.open(encoding="utf8") as old_file:
            old_content = json.load(old_file)

    with IgnoreSignals():
        with path.open(mode="w", encoding="utf8") as dump_file:
            json.dump(content, dump_file)

    return old_content
