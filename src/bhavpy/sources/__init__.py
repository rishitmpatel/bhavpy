"""One module per upstream data source.

Each module knows exactly one URL family and one file format, and turns it into a
DataFrame with bhavpy's canonical column names. When an exchange changes a URL or a
column, the fix belongs in a single module here; nothing else should need to change.
"""
