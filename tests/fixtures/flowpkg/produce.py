"""Produces the 'signal' column as a dict-literal, and writes 'flag' by subscript."""


def compute(df):
    df['flag'] = 0                 # subscript write -> produces 'flag'
    return {'signal': df, 'meta': 1}  # dict-literal key -> produces 'signal', 'meta'
