class SddError(Exception):
    """Base error for the SDD framework."""


class ConfigError(SddError):
    pass


class PathSafetyError(SddError):
    pass


class RegistryError(SddError):
    pass


class DiscoveryError(SddError):
    pass


class GovernanceError(SddError):
    pass


class ApprovalRequired(GovernanceError):
    pass
