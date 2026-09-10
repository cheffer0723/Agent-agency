from dotenv import load_dotenv
from agency_swarm import Agency

from chief_of_staff import chief_of_staff
from beta_support import beta_support

load_dotenv()

# do not remove this method, it is used in the main.py file to deploy the agency (it has to be a method)
def create_agency(load_threads_callback=None):
    # Two entry points serving different audiences:
    #  - chief_of_staff: internal, founder-facing scope/release manager.
    #  - beta_support:   external, tester-facing support for Asymmetry's beta.
    # For a public tester deployment you would typically expose only beta_support.
    agency = Agency(
        chief_of_staff,
        beta_support,
        name="ChiefOfStaffAgency",
        shared_instructions="shared_instructions.md",
        load_threads_callback=load_threads_callback,
    )

    return agency

if __name__ == "__main__":
    agency = create_agency()

    # run in terminal
    agency.terminal_demo()
