"""Infrastructure layer: concrete adapters for domain ports.

This is the only layer allowed to import third-party libraries
(web3, eth_account, sqlite3, ...). Everything here is replaceable
without touching the domain or application layers.
"""
