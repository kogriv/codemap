"""Consumes the 'signal' column by subscript read."""


def plot(frame):
    series = frame['signal']       # subscript read -> consumes 'signal'
    return series
