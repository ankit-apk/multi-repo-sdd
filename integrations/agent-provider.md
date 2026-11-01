# Agent provider

The Guardian does not import an agent SDK.

```text
AgentProvider
  submit(packet) -> AgentResult
  cancel(packet) -> None
```

`ImplementationPacket` carries the change id, repository path, and the approved spec, design, and task files. `read_only` is true unless both `sdd change implement --authorize-writes` and `governance.authorize_repository_writes: true` are set.

`LocalPacketProvider` writes those packets under the change directory.

`CommandAgentProvider` executes `agents.implementation_command` with `shell=False`. Environment variables describe the packet. The provider does not read the specification for shell syntax. A timeout comes from `agents.implementation_timeout_seconds`.

Repository discovery is not an agent product either. It is a Python scan with language adapters. The prompt in `prompts/discovery.md` is for a coding agent that is asked to extend or review discovery, not a second runtime.
