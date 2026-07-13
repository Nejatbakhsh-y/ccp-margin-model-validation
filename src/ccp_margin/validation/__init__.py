"""Independent validation tests for the CCP margin framework.

The modules in this package intentionally avoid importing private implementation
details from ``ccp_margin.models`` or ``ccp_margin.margin``. This preserves a
separate validation path for core calculations.
"""

from .benchmark_comparison import BenchmarkComparisonResult, compare_with_benchmark
from .christoffersen import (
    ChristoffersenConditionalCoverageResult,
    ChristoffersenIndependenceResult,
    christoffersen_conditional_coverage,
    christoffersen_independence,
)
from .implementation_verification import (
    ReconciliationResult,
    VerificationSuiteResult,
    independently_calculate_exception_flags,
    independently_calculate_portfolio_pnl,
    independently_calculate_returns,
    independently_calculate_total_margin,
    independently_calculate_var,
    reconcile_arrays,
    verify_implementation,
)
from .kupiec import KupiecResult, kupiec_unconditional_coverage
from .margin_shortfall import MarginShortfallResult, calculate_margin_shortfall
from .procyclicality import ProcyclicalityResult, assess_procyclicality
from .sensitivity import SensitivityResult, analyze_sensitivity
from .traffic_light import TrafficLightResult, basel_traffic_light

__all__ = [
    "BenchmarkComparisonResult",
    "ChristoffersenConditionalCoverageResult",
    "ChristoffersenIndependenceResult",
    "KupiecResult",
    "MarginShortfallResult",
    "ProcyclicalityResult",
    "ReconciliationResult",
    "SensitivityResult",
    "TrafficLightResult",
    "VerificationSuiteResult",
    "analyze_sensitivity",
    "assess_procyclicality",
    "basel_traffic_light",
    "calculate_margin_shortfall",
    "christoffersen_conditional_coverage",
    "christoffersen_independence",
    "compare_with_benchmark",
    "independently_calculate_exception_flags",
    "independently_calculate_portfolio_pnl",
    "independently_calculate_returns",
    "independently_calculate_total_margin",
    "independently_calculate_var",
    "kupiec_unconditional_coverage",
    "reconcile_arrays",
    "verify_implementation",
]
