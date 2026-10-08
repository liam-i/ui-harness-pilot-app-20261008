"""业务条件不满足与无法可信评估分别使用退出码 1 和 2。"""


class CheckError(Exception):
    def __init__(self, rule, message, *, refs=(), owner="integrator", unreadable=False):
        super().__init__(message)
        self.rule = rule
        self.refs = list(refs)
        self.owner = owner
        self.unreadable = unreadable

    def diagnostic(self):
        return {"rule_id": self.rule, "result": "unreadable" if self.unreadable else "failed",
                "object_refs": self.refs, "evidence": str(self), "next_owner": self.owner}


class InputError(CheckError):
    def __init__(self, rule, message, **kwargs):
        super().__init__(rule, message, unreadable=True, **kwargs)
