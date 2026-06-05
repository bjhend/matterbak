"""
Provide class HashableMatterData
"""



class HashableMatterData(dict):
    """Extends the dict of a mattermost object by hash method to enable storing in a set

    This class can be initialized with the original dict of the mattermost object.
    """

    def __eq__(self, other):
        return self['id'] == other['id']

    def __hash__(self):
        return hash(self['id'])
