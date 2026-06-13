from scrapers.sites.fulbright import FulbrightScraper
from scrapers.sites.mastercard_foundation import MasterCardFoundationScraper
from scrapers.sites.educationusa import EducationUSAScraper
from scrapers.sites.chevening import CheveningScraper
from scrapers.sites.commonwealth_scholarship import CommonwealthScholarshipScraper
from scrapers.sites.educanada import EduCanadaScraper
from scrapers.sites.campusfrance import CampusFranceScraper
from scrapers.sites.bgf_france import BGFFranceScraper
from scrapers.sites.afdb_scholarships import AfDBScholarshipScraper
from scrapers.sites.mo_ibrahim import MoIbrahimScraper
from scrapers.sites.afterschoolafrica import AfterSchoolAfricaScraper

# Only After School Africa is active — it aggregates US/UK/Canada/France
# scholarships and is filtered to those countries in its scraper. The other
# source scrapers are kept importable below for easy re-enabling.
ALL_SCRAPERS = [
    AfterSchoolAfricaScraper,
]

# Disabled sources (re-add to ALL_SCRAPERS to re-enable):
_DISABLED_SCRAPERS = [
    FulbrightScraper,
    MasterCardFoundationScraper,
    EducationUSAScraper,
    CheveningScraper,
    CommonwealthScholarshipScraper,
    EduCanadaScraper,
    CampusFranceScraper,
    BGFFranceScraper,
    AfDBScholarshipScraper,
    MoIbrahimScraper,
]
