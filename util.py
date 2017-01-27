__author__ = 'mani'


class ClassProperty(object):
    """
    Can be used as a decorator to make a class property (without stacking @classmethod).
    """
    def __init__(self, f):
        self.f = f

    def __get__(self, instance, owner):
        return self.f(owner)


def identity(x):
    """identity function"""
    return x
