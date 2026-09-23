"""HTTP layer for the web app. Route handlers validate input, call one function
in agents/pm/* or tools/*, and serialise the result — no business logic here.
See docs/webapp-requirements.md §4.
"""
