#################################################################
# This script will retrieve all adGroups delta for a partner.
#################################################################

import json
import requests
import time
from typing import Any, List, Tuple

###########
# Constants
###########

# Define the GQL Platform API endpoint URLs.
EXTERNAL_SB_GQL_URL = 'https://ext-api.sb.thetradedesk.com/graphql'
PROD_GQL_URL = 'https://desk.thetradedesk.com/graphql'

#############################
# Variables for YOU to define
#############################

# Define the GraphQL Platform API endpoint URL this script will use.
gql_url = EXTERNAL_SB_GQL_URL

# Replace the placeholder value with your actual API token.
token = 'AUTH_TOKEN_PLACEHOLDER'

# Partner ID to retrive data for.
target_partner_id = 'PARTNER_ID_PLACEHOLDER'

# The minimum tracking version to start queying with. If 0, the current minimum tracking version will be fetched.
starting_minimum_tracking_version = 0

#############################
# Output variables
#############################

# This is the tracking version for the next iteration of fetching data.
next_change_tracking_version = 0

# A list holding the adGroups that have been updated and should be processed by your system.
changed_adgroups_list = []

################
# Helper Methods
################

show_timings = False

advertisers_chunk_size = 100

# Represents a response from the GQL server.
class GqlResponse:
  def __init__(self, data: dict[Any, Any], errors: List[Any]) -> None:
    # This is where the return data from the GQL operation is stored.
    self.data = data
    # This is where any errors from the GQL operation are stored.
    self.errors = errors


# Executes a GQL request to the specified gql_url, using the provided body definition and associated variables.
# This indicates if the call was successful and returns the `GqlResponse`.
def execute_gql_request(body, variables) -> Tuple[bool, GqlResponse]:
  # Create headers with the authorization token.
  headers: dict[str, str] = {
    'TTD-Auth': token
  }

  # Create a dictionary for the GraphQL request.
  data: dict[str, Any] = {
    'query': body,
    'variables': variables
  }

  # Send the GraphQL request.
  response = requests.post(url=gql_url, json=data, headers=headers)
  content = json.loads(response.content) if len(response.content) > 0 else {}

  if not response.ok:
    print('GQL request failed!')
    # For more verbose error messaging, uncomment the following line:
    # print(response)

  # Parse any data if it exists, otherwise, return an empty dictionary.
  resp_data = content.get('data', {})
  # Parse any errors if they exist, otherwise, return an empty error list.
  errors = content.get('errors', [])

  return (response.ok, GqlResponse(resp_data, errors))

def log_timing(text:str, start_time, end_time) -> str:
  if show_timings:
    print(f'{text}: {(end_time - start_time):.2f} seconds')

# A GQL query to retrieve all advertisers globally.
def get_all_advertisers(partner_id: str, cursor: str) -> Any:
  after_clause = f'after: "{cursor}",' if cursor else ''

  query = f"""
  query GetAdvertisers($partnerId: String!) {{
    advertisers(
      where: {{
        partnerId: {{ eq: $partnerId }}
      }}
      {after_clause}
      first: 1000) {{
      nodes {{
        id
      }}
      pageInfo {{
        endCursor
        hasNextPage
      }}
    }}
  }}"""

  # Define the variables in the query.
  variables: dict[str, Any] = {
    'partnerId': partner_id
  }

  # Send the GraphQL request.
  request_success, response = execute_gql_request(query,variables)

  if not request_success:
    print(response.errors)
    raise Exception('Failed to fetch advertisers.')

  return response.data


# A GQL query to retrieve the current minimum tracking version for an advertiser.
def get_current_minimum_tracking_version(advertiser_id: str) -> Any:
  query = """
  query GetAdGroupsDeltaMinimumVersion($advertiserIds: [ID!]!) {
    adGroupDelta(
      input: {
        advertiser: {
          changeTrackingVersion: 0
          ids: $advertiserIds
        }
      }
    ) {
      currentMinimumTrackingVersion
    }
  }"""

  # Define the variables in the query.
  variables: dict[str, Any] = {
    'advertiserIds': [advertiser_id]
  }

  # Send the GraphQL request.
  request_success, response = execute_gql_request(query, variables)

  if not request_success:
    print(response.errors)
    raise Exception('Failed to retrieve current minimum tracking version.')

  return response.data['adGroupDelta']['currentMinimumTrackingVersion']


# A GQL query to retrieve the adGroups delta for an advertiser.
def get_adgroups_delta(advertiser_ids: list[str], change_tracking_version: int) -> Any:
  query = """
  query GetAdGroupsDelta($changeTrackingVersion: Long!, $advertiserIds: [ID!]!) {
    adGroupDelta(
      input: {
        advertiser: {
          changeTrackingVersion: $changeTrackingVersion
          ids: $advertiserIds
        }
      }
    ) {
      nextChangeTrackingVersion
      adGroups {
        id
        name
        advertiser {
          id
        }
        campaign {
          id
        }
        isHighFillRate
        isArchived
        creatives {
          nodes {
            id
          }
        }
      }
    }
  }"""

  # Define the variables in the query.
  variables: dict[str, Any] = {
    'changeTrackingVersion': change_tracking_version,
    'advertiserIds': advertiser_ids
  }

  # Send the GraphQL request.
  request_success, response = execute_gql_request(query, variables)

  if not request_success:
    print(response.errors)
    raise Exception('Failed to retrieve adGroup delta.')

  return response.data['adGroupDelta']


########################################################
# Execution Flow:
#  1. Retrieve advertisers IDs (limit to advertisers_chunk_size at a time).
#  2. Get the minimum tracking version.
#  3. Retrieve all the adGroup deltas.
########################################################
advertiser_ids = []
has_next = True
cursor = None

start_time = time.time()

while has_next:
  print(f"Retrieving advertisers after cursor: {cursor}")
  advertiser_data = get_all_advertisers(target_partner_id, cursor)

  # Retrieve advertiser IDs.
  for node in advertiser_data['advertisers']['nodes']:
    advertiser_ids.append(node['id'])

  # Update pagination information.
  has_next = advertiser_data['advertisers']['pageInfo']['hasNextPage']
  cursor = advertiser_data['advertisers']['pageInfo']['endCursor']

print(f'Number of advertiserIds: {len(advertiser_ids)}')

# Get the current minimum tracking version if a `starting_minimum_tracking_version` is not specified.
minimum_tracking_version = get_current_minimum_tracking_version(advertiser_ids[0]) if starting_minimum_tracking_version == 0 else starting_minimum_tracking_version
print(f'Minimum tracking version: {minimum_tracking_version}')

# Retrieve adGroups. Splitting advertisers list into chunks of advertisers_chunk_size.
advertiser_chunks = [advertiser_ids[i:i + advertisers_chunk_size] for i in range(0, len(advertiser_ids), advertisers_chunk_size)]

i = 0
for chunk in advertiser_chunks:
  print(f'Processing chunk {i}')
  chunk_start_time = time.time();
  i += 1

  # Get adGroups for this chunk of advertisers.
  data = get_adgroups_delta(chunk, minimum_tracking_version)

  for adGroup in data['adGroups']:
    changed_adgroups_list.append(adGroup)

  # Ensure that we capture next change tracking version if we do not have it yet.
  if next_change_tracking_version == 0:
    next_change_tracking_version = data['nextChangeTrackingVersion']

  chunk_end_time = time.time();
  log_timing('Chunk processing time', chunk_start_time, chunk_end_time)

# All done.
end_time = time.time()

# Output data.
print();
print('Output data:')
print(f'Next minimum change tracking version: {next_change_tracking_version}')
print(f'Changed adGroups count: {len(changed_adgroups_list)}')
log_timing('Total processing time', start_time, end_time);
