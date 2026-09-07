from dataclasses import dataclass


@dataclass(frozen=True)
class ReportFilter:
    personnel_code: str = ""
    personnel_name: str = ""

    @property
    def is_filtered(self) -> bool:
        return bool(self.personnel_code)

    @classmethod
    def from_request(cls, request) -> "ReportFilter":
        return cls(
            personnel_code=(request.GET.get("personnel_code") or request.POST.get("personnel_code") or "").strip(),
            personnel_name=(request.GET.get("personnel_name") or request.POST.get("personnel_name") or "").strip(),
        )
