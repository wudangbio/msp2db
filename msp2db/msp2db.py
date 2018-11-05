#!/usr/bin/env python
from __future__ import absolute_import, unicode_literals, print_function
import datetime
import sqlite3
import argparse
import textwrap
import re
import collections
import os
import pubchempy as pcp
import uuid
import six

try:
    # For Python 3.0 and later
    from urllib.request import URLError
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import URLError

try:
    from http.client import BadStatusLine
except ImportError:
    from httplib import BadStatusLine


def create_db(file_pth=None, db_type='sqlite', db_name=None, user='', password='', schema="mona"):
    print("CREATE DB")
    if db_type == 'sqlite':
        conn = sqlite3.connect(file_pth)
        c = conn.cursor()

        c.execute('DROP TABLE IF EXISTS library_spectra_source')
        c.execute('''CREATE TABLE library_spectra_source (
                              id integer PRIMARY KEY,
                              name text NOT NULL
                              )'''
                  )


        c.execute('DROP TABLE IF EXISTS metab_compound')
        c.execute('''CREATE TABLE metab_compound (
                      inchikey_id text PRIMARY KEY,
                      name text,
                      pubchem_id text,
                      chemspider_id text,
                      other_names text,
                      exact_mass real,
                      molecular_formula text,
                      molecular_weight real,  
                      compound_class text,
                      smiles text,
                      created_at date,
                      updated_at date

                                               )''')

        c.execute('DROP TABLE IF EXISTS library_spectra_meta')
        c.execute('''CREATE TABLE library_spectra_meta (
                                       id integer PRIMARY KEY,
                                       name text,
                                       collision_energy text,
                                       ms_level real,
                                       accession text NOT NULL,
                                       resolution text,
                                       polarity integer,
                                       fragmentation_type text,
                                       precursor_mz real,
                                       precursor_type text,
                                       instrument_type text,
                                       instrument text,
                                       copyright text,
                                       column text,
                                       mass_accuracy real,
                                       mass_error real,                                                                 
                                       origin text,

                                       library_spectra_source_id integer NOT NULL,
                                       inchikey_id text NOT NULL,

                                       FOREIGN KEY(library_spectra_source_id) REFERENCES library_spectra_source(id),
                                       FOREIGN KEY(inchikey_id) REFERENCES metab_compound(inchikey_id)
                                       )'''
                      )

        c.execute('DROP TABLE IF EXISTS library_spectra')
        c.execute('''CREATE TABLE library_spectra (
                                              id integer PRIMARY KEY,
                                              mz real NOT NULL,
                                              i real NOT NULL,
                                              other text,
                                              library_spectra_meta_id integer NOT NULL,
                                              FOREIGN KEY (library_spectra_meta_id) REFERENCES library_spectra_meta(id)
                                              )'''
                  )


def get_meta_regex(schema='massbank'):
    # NOTE: will just ignore cases, to avoid repetition here
    meta_parse = collections.OrderedDict()

    if schema == 'mona':
        meta_parse['collision_energy'] = ['^collision energy(?:=|:)(.*)$']
        meta_parse['ms_level'] = ['^ms.*level(?:=|:)\D*(\d*)$', '^ms type(?:=|:)\D*(\d*)$',
                              '^Spectrum_type(?:=|:)\D*(\d*)$']
        meta_parse['accession'] = ['^accession(?:=|:)(.*)$', '^DB#(?:=|:)(.*)$']
        meta_parse['resolution'] = ['^resolution(?:=|:)(.*)$']
        meta_parse['polarity'] = ['^ion.*mode(?:=|:)(.*)$', '^ionization.*mode(?:=|:)(.*)$', '^polarity(?:=|:)(.*)$']
        meta_parse['fragmentation_type'] = ['^fragmentation.*mode(?:=|:)(.*)$', '^fragmentation.*type(?:=|:)(.*)$']
        meta_parse['precursor_mz'] = ['^precursor m/z(?:=|:)(\d*[.,]?\d*)$', '^precursor.*mz(?:=|:)(\d*[.,]?\d*)$']
        meta_parse['precursor_type'] = ['^precursor.*type(?:=|:)(.*)$', '^adduct(?:=|:)(.*)$']
        meta_parse['instrument_type'] = ['^instrument.*type(?:=|:)(.*)$']
        meta_parse['instrument'] = ['^instrument(?:=|:)(.*)$']
        meta_parse['copyright'] = ['^copyright(?:=|:)(.*)$']
        # meta_parse['column'] = ['^column(?:=|:)(.*)$']
        meta_parse['mass_accuracy'] = ['^mass.*accuracy(?:=|:)(\d*[.,]?\d*)$']
        meta_parse['mass_error'] = ['^mass.*error(?:=|:)(\d*[.,]?\d*)$']
        meta_parse['origin'] = ['^origin(?:=|:)(.*)$']
        meta_parse['name'] = ['^Name(?:=|:)(.*)$']

    elif schema == 'massbank':
        meta_parse['collision_energy'] = ['^AC\$MASS_SPECTROMETRY:\s+COLLISION_ENERGY\s+(.*)$']
        meta_parse['ms_level'] = ['^AC\$MASS_SPECTROMETRY:\s+MS_TYPE\s+\D*(\d*)$']
        meta_parse['accession'] = ['^ACCESSION:(.*)$']
        meta_parse['resolution'] = ['^AC\$MASS_SPECTROMETRY:\s+RESOLUTION\s+(.*)$']
        meta_parse['polarity'] = ['^AC\$MASS_SPECTROMETRY:\s+ION_MODE\s+(.*)$']
        meta_parse['fragmentation_type'] = ['^AC\$MASS_SPECTROMETRY:\s+FRAGMENTATION_MODE\s+(.*)$']
        meta_parse['precursor_mz'] = ['^MS\$FOCUSED_ION:\s+PRECURSOR_M/Z\s+(\d*[.,]?\d*)$']
        meta_parse['precursor_type'] = ['^MS\$FOCUSED_ION:\s+PRECURSOR_TYPE\s+(.*)$']
        meta_parse['instrument_type'] = ['^AC\$INSTRUMENT_TYPE:\s+(.*)$']
        meta_parse['instrument'] = ['^AC\$INSTRUMENT:\s+(.*)$']
        meta_parse['copyright'] = ['^COPYRIGHT:\s+(.*)']
        # meta_parse['column'] = ['^column(?:=|:)(.*)$']
        meta_parse['mass_accuracy'] = ['^AC\$MASS_SPECTROMETRY:\s+ACCURACY\s+(.*)$']  # need to check
        meta_parse['mass_error'] = ['^AC\$MASS_SPECTROMETRY:\s+ERROR\s+(.*)$']  # need to check
        meta_parse['origin'] = ['^origin(?:=|:)(.*)$']
        meta_parse['name'] = ['^RECORD_TITLE:\s+(.*)$']



    return meta_parse


def get_compound_regex(schema='mona'):
    # NOTE: will just ignore cases, to avoid repetition here
    meta_parse = collections.OrderedDict()

    if schema == 'mona':
        meta_parse['name'] = ['^Name(?:=|:)(.*)$']
        meta_parse['inchikey_id'] = ['^inchikey(?:=|:)(.*)$']
        meta_parse['molecular_formula'] = ['^molecular formula(?:=|:)(.*)$', '^formula:(.*)$']
        meta_parse['molecular_weight'] = ['^MW(?:=|:)(\d*[.,]?\d*)$']
        meta_parse['pubchem_id'] = ['^pubchem.*cid(?:=|:)(\d*)".*$']
        meta_parse['chemspider_id'] = ['^chemspider(?:=|:)(\d*)".*$']
        meta_parse['compound_class'] = ['^compound.*class(?:=|:)(.*)$']
        meta_parse['exact_mass'] = ['^exact.*mass(?:=|:)(\d*[.,]?\d*)$']
        meta_parse['smiles'] = ['^SMILES(?:=|:)(.*)$']
        meta_parse['other_names'] = ['^Synonym(?:=|:)(.*)$']
    elif schema == 'massbank':
        meta_parse['name'] = ['^CH\$NAME:\s+(.*)$']
        meta_parse['other_names'] = ['^CH\$NAME:\s+(.*)$']

        meta_parse['inchikey_id'] = ['^CH\$LINK:\s+INCHIKEY\s+(.*)$']
        meta_parse['molecular_formula'] = ['^CH\$FORMULA:\s+(.*)$']
        meta_parse['molecular_weight'] = ['^CH\$MOLECULAR_WEIGHT:\s+(.*)$']
        meta_parse['pubchem_id'] = ['^CH\$LINK:\s+PUBCHEM\s+CID:(.*)$']
        meta_parse['chemspider_id'] = ['^CH\$LINK:\s+CHEMSPIDER\s+(.*)$']
        meta_parse['compound_class'] = ['^CH\$COMPOUND_CLASS:\s+(.*)$']
        meta_parse['exact_mass'] = ['^CH\$EXACT_MASS:\s+(.*)$']
        meta_parse['smiles'] = ['^CH\$SMILES:\s+(.*)$']


    return meta_parse




def get_connection(db_type, db_pth, user, password, name):
    if db_type == 'sqlite':
        print(db_pth)
        conn = sqlite3.connect(db_pth)
    elif db_type == 'mysql':
        import mysql.connector
        conn = mysql.connector.connect(user=user, password=password, database=name)
    elif db_type == 'django_mysql':
        from django.db import connection as conn

    return conn


def removekey(d, key):
    r = dict(d)
    del r[key]
    return r


class LibraryData(object):
    def __init__(self, msp_pth, name, source, mslevel=0,
                 db_pth=None, db_type='sqlite', d_form=False, password='', user='',
                 chunk=0, schema = 'mona', user_meta_regex=None, user_compound_regex=None, celery_obj=False):

        conn = get_connection(db_type, db_pth, user, password, name)
        print('Starting library data parsing')
        self.c = conn.cursor()
        self.conn = conn

        self.meta_info_all = []
        self.compound_info_all = []
        self.compound_ids = []
        self.get_compound_ids()

        self.spectra_all = []
        self.start_spectra = False

        if user_meta_regex:
            self.meta_regex = user_meta_regex
        else:
            self.meta_regex = get_meta_regex(schema=schema)

        if user_compound_regex:
            self.compound_regex = user_meta_regex
        else:
            self.compound_regex = get_compound_regex(schema=schema)

        self.meta_info = self.get_blank_meta_info()

        self.compound_info = self.get_blank_compound_info()
        self.get_current_ids()
        self.name = name
        self.source = source
        self.mslevel = mslevel
        self.other_names = []

        if d_form:
            self.num_lines = sum(1 for line in msp_pth)
            self.update_lines(msp_pth,
                              chunk,
                              db_type,
                              initial_update_source=True,
                              celery_obj=celery_obj
                              )
        else:
            self.num_lines = sum(1 for line in open(msp_pth))
            with open(msp_pth, "rb") as f:
                self.update_lines(f, chunk, db_type, initial_update_source=True,
                                  celery_obj=celery_obj)

    def update_lines(self, f, chunk, db_type, initial_update_source=True, celery_obj=False):
        c = 0
        old = 0
        update_source = initial_update_source
        for i, line in enumerate(f):
            print(i, line)

            if i == 0:
                old = self.current_id_meta

            self.update_libdata(line)

            if self.current_id_meta > old:
                old = self.current_id_meta
                c += 1

            if c > chunk:

                if celery_obj:
                    celery_obj.update_state(state='current spectra {}'.format(str(i)),
                                            meta={'current': i, 'total': self.num_lines})
                print(self.current_id_meta)

                self.insert_data(update_source=update_source, remove_data=True, db_type=db_type)
                update_source = False
                c = 0

        self.insert_data(update_source=update_source, remove_data=True, db_type=db_type)

    def get_current_ids(self, source=True, meta=True, spectra=True):
        c = self.c
        # Get the last uid for the spectra_info table
        if source:
            c.execute('SELECT max(id) FROM library_spectra_source')
            last_id_origin = c.fetchone()[0]
            if last_id_origin:
                self.current_id_origin = last_id_origin + 1
            else:
                self.current_id_origin = 1

        if meta:
            c.execute('SELECT max(id) FROM library_spectra_meta')
            last_id_meta = c.fetchone()[0]

            if last_id_meta:
                self.current_id_meta = last_id_meta + 1
            else:
                self.current_id_meta = 1

        if spectra:
            c.execute('SELECT max(id) FROM library_spectra')
            last_id_spectra = c.fetchone()[0]

            if last_id_spectra:
                self.current_id_spectra = last_id_spectra + 1
            else:
                self.current_id_spectra = 1

    def get_compound_ids(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT inchikey_id FROM metab_compound')
        self.conn.commit()
        for row in cursor:
            if not row[0] in self.compound_ids:
                self.compound_ids.append(row[0])

    def update_libdata(self, line):

        if re.match('^Comment.*$', line, re.IGNORECASE):
            comments = re.findall('"([^"]*)"', line)
            for c in comments:
                self.parse_meta_info(c)
                self.parse_compound_info(c)

        self.parse_meta_info(line)
        self.parse_compound_info(line)

        if self.mslevel > 0:
            self.meta_info['ms_level'] = self.mslevel

        self.get_other_names(line)

        # num peaks
        if re.match('^Num Peaks(.*)$', line, re.IGNORECASE) or \
                re.match('^PK\$PEAK: m/z int\. rel\.int\.$', line, re.IGNORECASE):

            # In the mass bank msp files, sometimes the precursor_mz is missing but we have the neutral mass and
            # the precursor_type (e.g. adduct) so we can calculate the precursor_mz

            if not self.meta_info['precursor_mz'] and self.meta_info['precursor_type'] and self.compound_info[
                'exact_mass']:
                self.meta_info['precursor_mz'] = get_precursor_mz(float(self.compound_info['exact_mass']),
                                                                  self.meta_info['precursor_type'])

            if not self.meta_info['polarity']:
                # have to do special check for polarity (as sometimes gets missed)
                m = re.search('^\[.*\](\-|\+)', self.meta_info['precursor_type'], re.IGNORECASE)
                if m:
                    polarity = m.group(1).strip()
                    if polarity == '+':
                        self.meta_info['polarity'] = 'positive'
                    elif polarity == '-':
                        self.meta_info['polarity'] = 'negative'


            other_name_l = [name for name in self.other_names if name != self.compound_info['name']]
            self.compound_info['other_names'] = ' <#> '.join(other_name_l)



            if not self.compound_info['inchikey_id']:
                self.set_inchi_pcc(self.compound_info['pubchem_id'], 'cid', 0)

            if not self.compound_info['inchikey_id']:
                self.set_inchi_pcc(self.compound_info['smiles'], 'smiles', 0)

            if not self.compound_info['inchikey_id']:
                self.set_inchi_pcc(self.compound_info['name'], 'name', 0)

            if not self.compound_info['inchikey_id']:
                print('WARNING, cant get inchi key for ', self.compound_info)
                print(self.meta_info)
                print('#########################')
                self.compound_info['inchikey_id'] = 'UNKNOWN_' + str(uuid.uuid4())

            if not self.compound_info['pubchem_id'] and self.compound_info['inchikey_id']:
                self.set_inchi_pcc(self.compound_info['inchikey_id'], 'inchikey', 0)

            if not self.compound_info['name']:
                self.compound_info['name'] = 'unknown name'

            if not self.compound_info['inchikey_id'] in self.compound_ids:

                self.compound_info_all.append(tuple(self.compound_info.values()) + (
                                                                                    str(datetime.datetime.now()),
                                                                                    str(datetime.datetime.now()),
                                                                                    ))
                self.compound_ids.append(self.compound_info['inchikey_id'])

            if not self.meta_info['accession']:
                self.meta_info['accession'] = 'unknown accession'

            self.meta_info_all.append(
                (str(self.current_id_meta),) +
                tuple(self.meta_info.values()) +
                (str(self.current_id_origin), self.compound_info['inchikey_id'],)
            )

            # Reset the temp meta information
            self.meta_info = self.get_blank_meta_info()
            self.compound_info = self.get_blank_compound_info()
            self.other_names = []

            self.start_spectra = True
            return

        if self.start_spectra:
            if line in ['\n', '\r\n', '//\n', '//\r\n']:
                self.start_spectra = False
                self.current_id_meta += 1
                return

            splist = line.split()

            if len(splist) > 2:
                additional_info = ''.join(map(str, splist[2:len(splist)]))
            else:
                additional_info = ''

            srow = (
                self.current_id_spectra, float(splist[0]), float(splist[1]), additional_info,
                self.current_id_meta)

            self.spectra_all.append(srow)

            self.current_id_spectra += 1

    def get_blank_meta_info(self):
        return {k: '' for k in self.meta_regex.keys()}

    def get_blank_compound_info(self,):
        return {k: '' for k in self.compound_regex.keys()}

    def set_inchi_pcc(self, in_str, pcp_type, elem):
        if not in_str:
            return 0

        try:
            pccs = pcp.get_compounds(in_str, pcp_type)
        except pcp.BadRequestError as e:
            print(e)
            return 0
        except pcp.TimeoutError as e:
            print(e)
            return 0
        except urllib2.URLError as e:
            print(e)
            return 0
        except BadStatusLine as e:
            print(e)
            return 0

        if pccs:
            pcc = pccs[elem]
            self.compound_info['inchikey_id'] = pcc.inchikey
            self.compound_info['pubchem_id'] = pcc.cid
            self.compound_info['molecular_formula'] = pcc.molecular_formula
            self.compound_info['molecular_weight'] = pcc.molecular_weight
            self.compound_info['exact_mass'] = pcc.exact_mass
            self.compound_info['smiles'] = pcc.canonical_smiles

            if len(pccs) > 1:
                print('WARNING, multiple compounds for ', self.compound_info)

    def get_other_names(self, line):
        m = re.search(self.compound_regex['other_names'][0], line, re.IGNORECASE)
        if m:

            self.other_names.append(m.group(1).strip())
            print('OTHER NAMES!!!!!!!!!!!!!!!!!!!!!!', self.other_names)

    def parse_meta_info(self, line):

        for k, regexes in six.iteritems(self.meta_regex):
            for reg in regexes:
                m = re.search(reg, line, re.IGNORECASE)
                if m:
                    self.meta_info[k] = m.group(1).strip()

    def parse_compound_info(self, line):

        for k, regexes in six.iteritems(self.compound_regex):
            for reg in regexes:
                if self.compound_info[k]:
                    continue
                m = re.search(reg, line, re.IGNORECASE)
                if m:
                    self.compound_info[k] = m.group(1).strip()

    def insert_data(self, update_source, remove_data=False, schema='mona', db_type='sqlite'):
        # print "INSERT DATA"

        if update_source:
            # print "insert ref id"
            self.c.execute(
                "INSERT INTO library_spectra_source (id, name) VALUES ({a}, '{b}')".format(a=self.current_id_origin,
                                                                                           b=self.source))
            self.conn.commit()

        if self.compound_info_all:
            self.compound_info_all = make_sql_compatible(self.compound_info_all)

            cn = ', '.join(self.compound_info.keys()) + ',created_at,updated_at'

            insert_query_m(self.compound_info_all, columns=cn, conn=self.conn, table='metab_compound',
                           db_type=db_type)

        self.meta_info_all = make_sql_compatible(self.meta_info_all)

        cn = 'id,' + ', '.join(self.meta_info.keys()) + ',library_spectra_source_id, inchikey_id'

        insert_query_m(self.meta_info_all, columns=cn, conn=self.conn, table='library_spectra_meta',
                       db_type=db_type)


        cn = "id, mz, i, other, library_spectra_meta_id"
        insert_query_m(self.spectra_all, columns=cn, conn=self.conn, table='library_spectra', db_type=db_type)

        # self.conn.close()
        if remove_data:
            self.meta_info_all = []
            self.spectra_all = []
            self.compound_info_all = []
            self.get_current_ids(source=False)


def chunk_query(l, n, cn, conn, name, db_type):
    # For item i in a range that is a length of l,
    [insert_query_m(l[i:i + n], name, conn, cn, db_type) for i in range(0, len(l), n)]


def insert_query_m(data, table, conn, columns=None, db_type='mysql'):
    if len(data) > 10000:
        chunk_query(data, 10000, columns, conn, table, db_type)
    else:
        if db_type == 'sqlite':
            type_sign = '?'
        else:
            type_sign = '%s'
        type_com = type_sign + ", "
        print(data)
        type = type_com * (len(data[0]) - 1)
        type = type + type_sign

        if columns:
            stmt = "INSERT INTO " + table + "( " + columns + ") VALUES (" + type + ")"
        else:
            stmt = "INSERT INTO " + table + " VALUES (" + type + ")"
        print(stmt)

        cursor = conn.cursor()
        cursor.executemany(stmt, data)
        conn.commit()


def make_sql_compatible(ll):
    new_ll = []
    for l in ll:
        new_l = ()
        for i in l:
            if not i:
                new_l = new_l + (None,)
            else:
                if isinstance(i, str):
                    val = i.decode('utf8').encode('ascii', errors='ignore')
                else:
                    val = i
                new_l = new_l + (val,)
        new_ll.append(new_l)

    return new_ll


def get_precursor_mz(exact_mass, precursor_type):
    # these are just taken from what was present in the massbank .msp file for those missing the exact mass
    d = {'[M-H]-': -1.007276,
         '[M+H]+': 1.007276,
         '[M+H-H2O]+': 1.007276 - ((1.007276 * 2) + 15.9949)
         }

    try:

        return exact_mass + d[precursor_type]
    except KeyError as e:
        print(e)
        return False