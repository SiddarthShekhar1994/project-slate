"""Problems and topics read from a student's own course materials.

A review sheet or past exam is read by Claude into structured problems
(``read.py``). SymPy computes every answer key from that structure
(``kinds.py``) and the problem is used only if the key agrees with the
answer Claude gave when it read the sheet (``verify.py``). Topics that no
built-in skill covers become the student's own skills (``topics.py``), with
practice drawn from the sheet and from similar problems Claude writes
(``variants.py``), checked the same way.
"""
