"""The fictional companies, boards and postings of the demo world.

Every company, product and posting below is invented; a resemblance to a real organisation is a
coincidence. A posting is described by its attributes only: :mod:`jobs_radar.demo.render` turns the
same record into the posting text and into the "model's" extraction, so the two always agree and
every quote is verbatim.

The timeline has ``WEEKS`` weeks. A posting is on its board from ``first_week`` until
``last_week`` (``None`` = still open), which is what gives the trends and the lifecycle data.
"""

from dataclasses import dataclass

from jobs_radar.domain.enums import SourceType

# Ten weeks of history, oldest first; the last week is "this week".
WEEKS = 10


@dataclass(frozen=True)
class DemoCompany:
    """A fictional employer."""

    name: str
    website: str


@dataclass(frozen=True)
class DemoSource:
    """A fictional board: one company's ATS board or a job board with many employers."""

    key: str
    source_type: SourceType
    identifier: str
    company: str | None = None
    # When set, the last run of this board fails with this stable error class (a realistic red row).
    failing: str | None = None


@dataclass(frozen=True)
class DemoJob:
    """One posting, described by the attributes the demo needs."""

    title: str
    company: str
    source: str
    role: str
    pitch: str
    first_week: int
    last_week: int | None = None
    mode: str = "remote"
    places: tuple[str, ...] = ("Remote - EU",)
    regions: tuple[str, ...] = ("EU",)
    office_days: int = 2
    employment: tuple[str, ...] = ("employee_permanent",)
    hours: str = "full_time"
    seniority: tuple[str, ...] = ("senior",)
    years: int | None = None
    sector: str = "software_saas"
    secondary_sectors: tuple[str, ...] = ()
    must: tuple[str, ...] = ()
    nice: tuple[str, ...] = ()
    # (form, minimum, maximum) with form "annual_salary" or "day_rate"; EUR only (no conversion).
    pay: tuple[str, int, int] | None = None
    benefits: tuple[str, ...] = ()
    employer: str = "direct_employer"
    # The title of the posting this one repeats on another board (a duplicate listing).
    twin: str | None = None
    # True when the posting appears on the second run of its first week (the last run is "today").
    late: bool = False
    # The pay on the last run, when the employer changed it (a material change for the inbox).
    pay_update: tuple[str, int, int] | None = None


COMPANIES: dict[str, DemoCompany] = {
    "parcelwise": DemoCompany("Parcelwise", "https://parcelwise.example"),
    "quillstream": DemoCompany("Quillstream", "https://quillstream.example"),
    "fernhill": DemoCompany("Fernhill Analytics", "https://fernhill-analytics.example"),
    "orbitry": DemoCompany("Orbitry Cloud", "https://orbitry.example"),
    "brightwave": DemoCompany("Brightwave Telecom", "https://brightwave-telecom.example"),
    "cobaltridge": DemoCompany("Cobaltridge Bank", "https://cobaltridge.example"),
    "tidepool": DemoCompany("Tidepool Health", "https://tidepool-health.example"),
    "kestrel": DemoCompany("Kestrel Games", "https://kestrel-games.example"),
    "lumenharbor": DemoCompany("Lumen Harbor Energy", "https://lumenharbor.example"),
    "northbeam": DemoCompany("Northbeam Systems", "https://northbeam-systems.example"),
    "alderpine": DemoCompany("Alder & Pine Staffing", "https://alderpine-staffing.example"),
}

SOURCES: tuple[DemoSource, ...] = (
    DemoSource("parcelwise", SourceType.GREENHOUSE, "parcelwise", "parcelwise"),
    DemoSource("orbitry", SourceType.GREENHOUSE, "orbitry", "orbitry"),
    DemoSource("cobaltridge", SourceType.GREENHOUSE, "cobaltridge", "cobaltridge"),
    DemoSource("kestrel", SourceType.GREENHOUSE, "kestrel", "kestrel", failing="rate_limited"),
    DemoSource("quillstream", SourceType.ASHBY, "quillstream", "quillstream"),
    DemoSource("fernhill", SourceType.LEVER, "fernhill", "fernhill"),
    DemoSource("brightwave", SourceType.LEVER, "brightwave", "brightwave"),
    DemoSource("tidepool", SourceType.SMARTRECRUITERS, "tidepool", "tidepool"),
    DemoSource("arbeitnow", SourceType.ARBEITNOW, "arbeitnow"),
    DemoSource("remotive", SourceType.REMOTIVE, "remotive"),
)

_PT = ("Remote, Portugal",)
_PT_REGION = ("Portugal",)

JOBS: tuple[DemoJob, ...] = (
    # --- Parcelwise: logistics software, remote-first ---------------------------------------
    DemoJob(
        "Senior Backend Engineer, Tracking",
        "parcelwise",
        "parcelwise",
        "backend_engineering",
        "You will build and operate the event pipeline that tracks every parcel.",
        6,
        sector="logistics_transport",
        must=("Python", "PostgreSQL", "Kafka"),
        nice=("Kubernetes",),
        pay=("annual_salary", 68000, 82000),
        benefits=("learning_budget", "flexible_hours"),
        years=6,
    ),
    DemoJob(
        "Staff Data Platform Engineer",
        "parcelwise",
        "parcelwise",
        "data_engineering",
        "You will own the data platform behind routing, pricing and delivery estimates.",
        3,
        places=_PT,
        regions=_PT_REGION,
        seniority=("staff_principal",),
        sector="logistics_transport",
        must=("Python", "Apache Airflow", "Kafka", "AWS", "Spark"),
        nice=("Terraform",),
        pay=("annual_salary", 88000, 104000),
        benefits=("equity", "learning_budget"),
        years=9,
    ),
    DemoJob(
        "Platform Engineer, Kubernetes",
        "parcelwise",
        "parcelwise",
        "devops_platform",
        "You will run the clusters and the deployment tooling used by forty engineers.",
        9,
        mode="hybrid",
        late=True,
        places=("Porto, Portugal",),
        regions=(),
        office_days=2,
        sector="logistics_transport",
        must=("Kubernetes", "Terraform", "AWS"),
        nice=("Go",),
        pay=("annual_salary", 60000, 72000),
        benefits=("home_office_budget",),
    ),
    DemoJob(
        "Frontend Engineer, Dispatch Console",
        "parcelwise",
        "parcelwise",
        "frontend_engineering",
        "You will build the console dispatchers use to re-route parcels in real time.",
        5,
        seniority=("mid",),
        sector="logistics_transport",
        must=("TypeScript", "React"),
        pay=("annual_salary", 50000, 62000),
    ),
    DemoJob(
        "Engineering Manager, Fleet",
        "parcelwise",
        "parcelwise",
        "software_engineering_general",
        "You will lead a team of eight engineers working on fleet planning.",
        2,
        7,
        seniority=("management",),
        sector="logistics_transport",
        must=("Python",),
        pay=("annual_salary", 78000, 92000),
    ),
    # --- Quillstream: data tooling, remote ----------------------------------------------------
    DemoJob(
        "Senior Data Engineer",
        "quillstream",
        "quillstream",
        "data_engineering",
        "You will build the ingestion layer that feeds our customers' warehouses.",
        4,
        must=("Python", "Apache Airflow", "PostgreSQL"),
        nice=("dbt",),
        pay=("annual_salary", 70000, 85000),
        benefits=("learning_budget",),
        years=5,
    ),
    DemoJob(
        "Backend Engineer, Go",
        "quillstream",
        "quillstream",
        "backend_engineering",
        "You will write the Go services that schedule and monitor customer pipelines.",
        7,
        seniority=("mid",),
        must=("Go", "PostgreSQL", "Kafka"),
        pay=("annual_salary", 55000, 68000),
        benefits=("flexible_hours",),
    ),
    DemoJob(
        "Machine Learning Engineer",
        "quillstream",
        "quillstream",
        "ai_ml_engineering",
        "You will train and serve the models that detect anomalies in customer data.",
        5,
        must=("Python", "PyTorch"),
        nice=("Kubernetes",),
        pay=("annual_salary", 72000, 90000),
    ),
    DemoJob(
        "Developer Advocate",
        "quillstream",
        "quillstream",
        "marketing_communications",
        "You will write, speak and run community events to grow our developer audience.",
        3,
        6,
        seniority=("mid",),
        must=("Public speaking",),
        pay=("annual_salary", 52000, 64000),
    ),
    DemoJob(
        "Junior Backend Developer",
        "quillstream",
        "quillstream",
        "backend_engineering",
        "You will join the platform team and learn our stack with a mentor.",
        3,
        seniority=("junior",),
        must=("Python",),
        pay=("annual_salary", 32000, 38000),
    ),
    # --- Fernhill Analytics ------------------------------------------------------------------
    DemoJob(
        "Analytics Engineer",
        "fernhill",
        "fernhill",
        "data_analysis",
        "You will model the data our analysts use for retail forecasts.",
        1,
        places=_PT,
        regions=_PT_REGION,
        seniority=("mid",),
        sector="retail_ecommerce",
        must=("SQL", "dbt"),
        nice=("Python",),
        pay=("annual_salary", 46000, 58000),
    ),
    DemoJob(
        "Senior Python Developer",
        "fernhill",
        "fernhill",
        "backend_engineering",
        "You will build the forecasting services that retailers call every hour.",
        2,
        mode="hybrid",
        places=("Lisbon, Portugal",),
        regions=(),
        office_days=3,
        sector="retail_ecommerce",
        must=("Python", "FastAPI", "PostgreSQL"),
        pay=("annual_salary", 58000, 70000),
    ),
    DemoJob(
        "Junior Data Analyst",
        "fernhill",
        "fernhill",
        "data_analysis",
        "You will prepare weekly reports and learn the forecasting models.",
        6,
        seniority=("junior",),
        sector="retail_ecommerce",
        must=("SQL",),
        pay=("annual_salary", 28000, 34000),
    ),
    # --- Orbitry Cloud: infrastructure -------------------------------------------------------
    DemoJob(
        "Senior Site Reliability Engineer",
        "orbitry",
        "orbitry",
        "devops_platform",
        "You will keep the control plane of our cloud platform fast and available.",
        0,
        sector="enterprise_it",
        must=("Kubernetes", "Terraform", "AWS"),
        nice=("Go",),
        pay=("annual_salary", 72000, 90000),
        benefits=("equity", "home_office_budget"),
        years=6,
    ),
    DemoJob(
        "Principal Cloud Architect",
        "orbitry",
        "orbitry",
        "solutions_architecture",
        "You will define the reference architectures our enterprise customers adopt.",
        4,
        seniority=("staff_principal",),
        sector="enterprise_it",
        must=("AWS", "Terraform"),
        pay=("annual_salary", 95000, 120000),
        benefits=("equity", "extra_leave"),
        years=10,
    ),
    DemoJob(
        "Backend Engineer, Billing Platform",
        "orbitry",
        "orbitry",
        "backend_engineering",
        "You will build the metering and invoicing services behind usage-based billing.",
        9,
        sector="enterprise_it",
        late=True,
        must=("Python", "PostgreSQL"),
        nice=("Kafka",),
        pay=("annual_salary", 64000, 78000),
        benefits=("learning_budget",),
    ),
    DemoJob(
        "Security Engineer, Cloud",
        "orbitry",
        "orbitry",
        "security",
        "You will harden the platform and run threat modelling for new services.",
        1,
        8,
        sector="enterprise_it",
        must=("AWS", "Terraform"),
        pay=("annual_salary", 68000, 84000),
    ),
    # --- Brightwave Telecom ------------------------------------------------------------------
    DemoJob(
        "Senior Software Engineer, Core Network",
        "brightwave",
        "brightwave",
        "software_engineering_general",
        "You will write the signalling software that runs inside our core network.",
        3,
        mode="onsite",
        places=("Madrid, Spain",),
        regions=(),
        sector="telecom",
        must=("C++", "Linux"),
        pay=("annual_salary", 62000, 76000),
    ),
    DemoJob(
        "Data Engineer, Network Analytics",
        "brightwave",
        "brightwave",
        "data_engineering",
        "You will build the streaming jobs that turn network events into insights.",
        5,
        mode="hybrid",
        places=("Lisbon, Portugal",),
        regions=(),
        office_days=3,
        sector="telecom",
        must=("Python", "Kafka", "Spark"),
        pay=("annual_salary", 56000, 70000),
    ),
    DemoJob(
        "Customer Support Specialist",
        "brightwave",
        "brightwave",
        "customer_support",
        "You will answer customer calls and solve billing questions.",
        2,
        mode="onsite",
        places=("Porto, Portugal",),
        regions=(),
        seniority=("junior",),
        sector="telecom",
        must=("Customer service",),
        pay=("annual_salary", 20000, 24000),
    ),
    # --- Cobaltridge Bank --------------------------------------------------------------------
    DemoJob(
        "Senior Backend Engineer, Payments",
        "cobaltridge",
        "cobaltridge",
        "backend_engineering",
        "You will build the payment APIs used by millions of cardholders.",
        0,
        mode="hybrid",
        places=("Porto, Portugal",),
        regions=(),
        office_days=2,
        sector="finance_banking",
        must=("Python", "PostgreSQL", "Kafka"),
        nice=("Kubernetes",),
        pay=("annual_salary", 62000, 76000),
        pay_update=("annual_salary", 66000, 80000),
        benefits=("health_insurance", "bonus"),
        years=7,
    ),
    DemoJob(
        "Financial Controller",
        "cobaltridge",
        "cobaltridge",
        "finance_accounting",
        "You will close the books each month and prepare the regulatory reports.",
        1,
        mode="onsite",
        places=("Frankfurt, Germany",),
        regions=(),
        sector="finance_banking",
        must=("IFRS",),
        pay=("annual_salary", 70000, 85000),
    ),
    DemoJob(
        "Data Engineer, Risk",
        "cobaltridge",
        "cobaltridge",
        "data_engineering",
        "You will build the pipelines that feed the credit risk models.",
        6,
        places=_PT,
        regions=_PT_REGION,
        sector="finance_banking",
        must=("Python", "Apache Airflow", "AWS", "Scala"),
        pay=("annual_salary", 58000, 72000),
        benefits=("health_insurance",),
    ),
    # --- Tidepool Health ---------------------------------------------------------------------
    DemoJob(
        "Backend Engineer, Patient Records",
        "tidepool",
        "tidepool",
        "backend_engineering",
        "You will build the APIs that hospitals use to share patient records safely.",
        4,
        sector="healthcare",
        must=("Python", "FastAPI", "PostgreSQL"),
        pay=("annual_salary", 58000, 72000),
        benefits=("health_insurance", "learning_budget"),
    ),
    DemoJob(
        "Full-stack Engineer",
        "tidepool",
        "tidepool",
        "software_engineering_general",
        "You will work across the booking app and the services behind it.",
        5,
        mode="hybrid",
        places=("Berlin, Germany",),
        regions=(),
        office_days=3,
        seniority=("mid",),
        sector="healthcare",
        must=("TypeScript", "Python"),
        pay=("annual_salary", 54000, 66000),
    ),
    DemoJob(
        "Data Engineer (B2B contract)",
        "tidepool",
        "tidepool",
        "data_engineering",
        "You will migrate the reporting pipelines to a streaming architecture.",
        7,
        places=_PT,
        regions=_PT_REGION,
        employment=("contractor_b2b",),
        sector="healthcare",
        must=("Python", "Kafka", "Apache Airflow"),
        pay=("day_rate", 450, 550),
    ),
    # --- Kestrel Games: gambling (the persona rejects the sector) ---------------------------
    DemoJob(
        "Senior Backend Engineer, Betting Engine",
        "kestrel",
        "kestrel",
        "backend_engineering",
        "You will build the low-latency engine that prices live bets.",
        2,
        sector="gambling",
        must=("Java", "Kafka", "PostgreSQL"),
        pay=("annual_salary", 75000, 95000),
    ),
    DemoJob(
        "Data Engineer, Player Analytics",
        "kestrel",
        "kestrel",
        "data_engineering",
        "You will build the pipelines behind player retention analytics.",
        5,
        sector="gambling",
        must=("Python", "Apache Airflow"),
        pay=("annual_salary", 62000, 78000),
    ),
    # --- Job boards: other employers and agencies --------------------------------------------
    DemoJob(
        "Python Developer (6-month contract)",
        "alderpine",
        "arbeitnow",
        "backend_engineering",
        "Our client needs a Python developer to extend an internal reporting tool.",
        6,
        employment=("contractor_agency",),
        employer="agency_recruiter",
        seniority=("mid",),
        sector="consulting_services",
        must=("Python", "Django"),
    ),
    DemoJob(
        "Senior Java Developer",
        "alderpine",
        "arbeitnow",
        "backend_engineering",
        "Our client, an insurer, is looking for a Java developer for a core platform.",
        3,
        mode="hybrid",
        places=("Munich, Germany",),
        regions=(),
        office_days=3,
        employer="agency_recruiter",
        sector="insurance",
        must=("Java", "Spring"),
        pay=("annual_salary", 65000, 80000),
    ),
    DemoJob(
        "Cloud Engineer, AWS",
        "northbeam",
        "remotive",
        "devops_platform",
        "You will migrate customer workloads to AWS and automate their deployment.",
        5,
        employment=("contractor_b2b",),
        sector="consulting_services",
        must=("AWS", "Terraform", "Python", "Azure"),
        pay=("day_rate", 480, 560),
    ),
    DemoJob(
        "Backend Developer",
        "lumenharbor",
        "arbeitnow",
        "backend_engineering",
        "You will build the services that forecast solar and wind production.",
        7,
        places=_PT,
        regions=_PT_REGION,
        seniority=("mid", "senior"),
        sector="energy_utilities",
        must=("Python", "PostgreSQL"),
    ),
    DemoJob(
        "Data Platform Lead",
        "lumenharbor",
        "remotive",
        "data_engineering",
        "You will lead the platform that collects readings from half a million smart meters.",
        9,
        seniority=("staff_principal",),
        sector="energy_utilities",
        must=("Kafka", "Python", "Apache Airflow"),
        late=True,
        benefits=("learning_budget", "extra_leave"),
        years=8,
    ),
    DemoJob(
        "Sales Engineer",
        "northbeam",
        "remotive",
        "sales_account_management",
        "You will demo our platform to prospects and help close enterprise deals.",
        4,
        seniority=("mid",),
        sector="enterprise_it",
        must=("Presentation skills",),
        pay=("annual_salary", 48000, 60000),
    ),
    DemoJob(
        "QA Automation Engineer (part-time)",
        "northbeam",
        "arbeitnow",
        "qa_testing",
        "You will automate regression tests for our web applications.",
        7,
        hours="part_time",
        seniority=("mid",),
        sector="enterprise_it",
        must=("Python", "Selenium"),
    ),
    # --- The same job on a second board (duplicate listings) -------------------------------
    DemoJob(
        "Senior Backend Engineer (Tracking)",
        "parcelwise",
        "remotive",
        "backend_engineering",
        "You will build and operate the event pipeline that tracks every parcel.",
        6,
        sector="logistics_transport",
        must=("Python", "PostgreSQL", "Kafka"),
        nice=("Kubernetes",),
        pay=("annual_salary", 68000, 82000),
        benefits=("learning_budget", "flexible_hours"),
        years=6,
        twin="Senior Backend Engineer, Tracking",
    ),
    DemoJob(
        "Senior SRE",
        "orbitry",
        "arbeitnow",
        "devops_platform",
        "You will keep the control plane of our cloud platform fast and available.",
        2,
        sector="enterprise_it",
        must=("Kubernetes", "Terraform", "AWS"),
        nice=("Go",),
        pay=("annual_salary", 72000, 90000),
        benefits=("equity", "home_office_budget"),
        years=6,
        twin="Senior Site Reliability Engineer",
    ),
)
