"""
.. module:: session
   :synopsis: Session management (login, logout, etc).
"""

import iso8601
from .bill import Bill
from .chartofaccount import ChartOfAccount
from .customer import Customer
from .invoice import Invoice
from .item import Item
from .vendor import Vendor
from .vendorcredit import VendorCredit
# removed the config module...
from .https import https_post
from .exceptions import BilldotcomError, ServerResponseError
import copy
import json

import requests

class Session(object):
    """
    This models and handles serialization of the Bill object.

    Sessions will time out after 35 minutes.

    You can use it in a with statement:

        >>> with Session():
        >>>     # do stuff
    """

    type_map = {
        'Bill': Bill,
        'ChartOfAccount': ChartOfAccount,
        'Customer': Customer,
        'Invoice': Invoice,
        'Item': Item,
        'Vendor': Vendor,
        'VendorCredit': VendorCredit
    }

    def __init__(self, session_id=None, api_key=None, 
                 username=None, password=None, org_id=None):
        self.session_id = session_id
        self.api_key = api_key 
        self.username = username
        self.password = password
        self.org_id = org_id

        if not self.session_id:
            if self.org_id:
                self.login()
            else:
                self.list_orgs()
        
    def post(self, url, data={}, **kwargs):
        if not self.session_id:
            error_msg = "cannot send POST request without logging in first"
            raise BilldotcomError(error_msg)

        payload = dict(
            devKey = self.api_key,
            sessionId = self.session_id
        )

        data = copy.deepcopy(data)
        data.update(kwargs)

        payload['data'] = json.dumps(data)

        return https_post(url, payload)

    def getcurrenttime(self):
        """Gets Bill.com's system time.

        Returns:
            datetime. System time as reported by Bill.com
        """
        response = self.post('CurrentTime.json')
        return iso8601.parse_date(response['currentTime'])

    def create(self, bdc_object):
        """Creates a Billdotcom object on the server.

        Args:
            bdc_object: A Billdotcom object with the required fields filled in.

        Returns:
            The newly created Object's ID.

        Raises:
            ServerResponseError
        """

        url = bdc_object.url
        data = dict(
            obj = bdc_object.data
        )

        response = self.post('Crud/Create/' + url, data)
        return response['id']

    def read(self, bdc_type, id):
        """Reads (gets) a Billdotcom object from the server.

        Args:
            bdc_type: A Billdotcom object type. Supported objects are:
                * Bill
                * ChartOfAccount
                * Customer
                * Invoice
                * Item
                * Vendor
                * VendorCredit

            id: the Id field of the object.

        Returns:
            The Billdotcom object or None.

        Raises:
            BilldotcomError
        """

        if bdc_type not in self.type_map:
            error_message = 'object type {} is not supported'.format(bdc_type)
            raise BilldotcomError(error_message)

        data = dict(
            id = id
        )

        try:
            response = self.post('Crud/Read/' + bdc_type + '.json', data)
            return self.type_map[response['entity']](**response)
        except ServerResponseError:
            return None

    def update(self, bdc_object):
        """Updates a Billdotcom object on the server. The id field is required.

        Args:
            bdc_object: A Billdotcom object with the required fields filled in.

        Raises:
            BilldotcomError, ServerResponseError
        """

        if 'id' not in bdc_object:
            raise BilldotcomError('the id field is required for updates')

        url = bdc_object.url
        data = dict(
            obj = bdc_object.data
        )

        self.post('Crud/Update/' + url, data)

    def delete(self, bdc_type, id):
        """Deletes (deactivates) a Billdotcom object on the server.

        Args:
            bdc_type: A Billdotcom object type. Supported objects are:
                * Bill
                * ChartOfAccount
                * Customer
                * Invoice
                * Item
                * Vendor
                * VendorCredit

            id: the Id field of the object.

        Raises:
            BilldotcomError
        """

        if bdc_type not in self.type_map:
            error_msg = 'object type {} is not supported'.format(bdc_type)
            raise BilldotcomError(error_msg)

        data = dict(
            id = id
        )

        self.post('Crud/Delete/' + bdc_type + '.json', data)

    def list(self, bdc_type, sort=[], filters=[], start=0, max=999,
             simple_response=True):
        """Lists Billdotcom objects on the server, with optional filters.
        The objects will be transformed into the corresponding classes
         and returned.

        Args:
            bdc_type: A Billdotcom object type. Supported objects are:
                * Bill
                * ChartOfAccount
                * Customer
                * Invoice
                * Item
                * Vendor
                * VendorCredit

            sort: A list of tuples representing sort order. 
            Use 'asc' for ascending and
                'desc' for descending. For example:
                 >>> with Session() as s:
                 >>>     s.list('Vendor', sort=[('createdTime', 'desc')])

            filters: A list of tuples representing filters to query with.

        Supported operators are:
                    =, <, >, !=, <=, >=, in, nin
                These operators can be used with any field in the model you are
                 querying, as long as it has a data type of ID, Date, DateTime,
                 or Enum. See the official Bill.com documentation for more on
                 this.
        
        An example of using a filter:
        >>> with Session() as s:
        >>>     s.get_list('bill', filters=[('invoiceDate', '<', date.today())])

            start: Start index for paging. Default 0.

            max: Maximum records returned. Default 999 (server maximum).

        Returns:
            List of objects from the server.

        Raises:
            BilldotcomError, ServerResponseError
        """

        if bdc_type not in self.type_map:
            err_msg = 'object type {} is not supported'.format(bdc_type)
            raise BilldotcomError(err_msg)

        data = dict(
            start = start,
            max = max
        )

        if sort:
            data['sort'] = [
                dict(field=name, asc=(order=='asc'))
                for name, order in sort
            ]

        if filters:
            data['filters']  = [
                dict(field=field, op=op, value=value)
                for field, op, value in filters
            ]

        response = self.post('List/{}.json'.format(bdc_type), data)

        if simple_response:
            return response

        return [self.type_map[row['entity']](**row) for row in response]

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, type, value, traceback):
        self.logout()

    def login(self):
        """Initiate a session on the server."""

        data = {
            'devKey': self.api_key,
            'userName': self.username,
            'password': self.password,
            'orgId': self.org_id
        }

        response = https_post('Login.json', data)

        self.session_id = response['sessionId']

    def list_orgs(self):
        print "Because no org_id was passed in (but other credentials were),"
        print " we'll get the list of orgs these credentials can access:"

        basic_login_creds = {

            'devKey'    : self.api_key,
            'userName'  : self.username,
            'password'  : self.password

        }

        org_infos = https_post('ListOrgs.json', {}, params=basic_login_creds)

        title = 'Got {0} organization(s):'.format(len(org_infos))
        print title
        print '-'*len(title)
        
        for org in org_infos:
            print '{orgId}\t{orgName}'.format(**org)
           
        if len(org_infos) == 1:
            print "OK, so since there's only one organization available to " \
                "this set of credentials, we'll just login to that org..."
            self.org_id = org_infos[0]['orgId']
            self.login()
        else:
            quit()
                     
    def logout(self):
        """Shut down a session on the server."""

        if not self.session_id:
            err_msg = "cannot logout on a session that has not logged in"
            raise BilldotcomError(err_msg)

        self.post('Logout.json')
        self.session_id = None
