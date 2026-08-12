"""A small, local Retrieval-Augmented Generation pipeline for legal contracts.

Flow:  load -> chunk -> embed+store  (ingestion)
       question -> embed -> search -> ground+cite  (query)
"""
