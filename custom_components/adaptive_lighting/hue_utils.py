"""Help fixing a serialization issue"""

from dataclasses import dataclass

@dataclass
class ResourceIdentifier:
    """
    Represent a ResourceIdentifier object as used by the Hue api.

    clip-api.schema.json#/definitions/ResourceIdentifierGet
    clip-api.schema.json#/definitions/ResourceIdentifierPost
    clip-api.schema.json#/definitions/ResourceIdentifierPut
    clip-api.schema.json#/definitions/ResourceIdentifierDelete
    """

    rid: str  # UUID
    rtype: str
