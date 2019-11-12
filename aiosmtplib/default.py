"""
A default enum, used for kwarg default values.
"""
import enum


class Default(enum.Enum):
    """
    Used for type hinting kwarg defaults.
    """

    token = 0


_default = Default.token
