"""Logic that is neither a route nor a row.

A router should read as a list of HTTP decisions — what status, what shape, who is
allowed. Everything underneath it that could be tested without a request lives here, so
that `security.py` can be exercised directly rather than through a POST.
"""
