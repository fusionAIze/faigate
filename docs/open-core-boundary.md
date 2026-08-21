# Open-Core Boundary

faigate's open core is the opinion router: catalog resolution, provider
selection, orchestration, and the API-key transport that calls upstreams with
faigate's own identity.

Identity follows the transport, not the routing core.

- **api_key — faigate's own identity.** The default. faigate authenticates
  upstream calls as itself (an opinion router acting on the operator's pooled
  key). This is the only identity the open core requires.

- **oauth relay — customer-owned identity.** An optional wrapper, implemented
  under `faigate/oauth/`, that executes upstream calls on the customer's own
  behalf using the customer's granted credentials. It is layered *around* the
  routing core and is never required for faigate to run.

The boundary: api_key is retained as the default identity path. The OAuth
relay is optional, separated from the routing core, and switches nothing about
how faigate routes — only whose identity is presented upstream. Removing the
OAuth package leaves the open core fully functional.
