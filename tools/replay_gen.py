#!/usr/bin/env python3

# @file
#
# Copyright 2022, Verizon Media
# SPDX-License-Identifier: Apache-2.0
#

import json
import argparse
import random
import uuid
import datetime
import pathlib
import shutil
import copy
import sys
from urllib.parse import urlparse

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedSeq

    has_yaml = True
    yaml = YAML()

    def flow_style_list(l):
        fsl = CommentedSeq(l)
        fsl.fa.set_flow_style()
        return fsl

except ModuleNotFoundError:
    has_yaml = False
    print('Module "ruamel.yaml" not found, please install using command "pip install ruamel.yaml".')
    print('Continuing with JSON format replay files.')

http_status_codes = {
    100: 'Continue',
    101: 'Switching Protocol',
    102: 'Processing',
    103: 'Early Hints',
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi-Status',
    208: 'Already Reported',
    226: 'IM Used',
    300: 'Multiple Choice',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    306: 'unused',
    307: 'Temporary Redirect',
    308: 'Permanent Redirect',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Payload Too Large',
    414: 'URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Range Not Satisfiable',
    417: 'Expectation Failed',
    418: 'I\'m a teapot',
    421: 'Misdirected Request',
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    425: 'Too Early',
    426: 'Upgrade Required',
    428: 'Precondition Required',
    429: 'Too Many Requests',
    431: 'Request Header Fields Too Large',
    451: 'Unavailable For Legal Reasons',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    506: 'Variant Also Negotiates',
    507: 'Insufficient Storage',
    508: 'Loop Detected',
    510: 'Not Extended',
    511: 'Network Authentication Required'
}


class ReplaySession:

    tls_vers = {1.1: 'TLSv1.1', 1.2: 'TLSv1.2', 1.3: 'TLSv1.3'}

    def __init__(self):
        self.url = ''
        self.hostname = ''
        self.path = ''
        self.tls_ver = 0
        self.http_ver = 1.1
        self.ip_ver = 4
        self.session = {}
        self.transactions = []
        return

    def random_populate(self, transaction_num, url_list, http_trans, tls_trans, h2_trans):

        # Grab a random url and strip out the hostname.
        # Also need to make sure the url matches the protocols we allow.
        if not http_trans:
            while True:
                if self.random_hostname(url_list):
                    self.random_tls_ver(not tls_trans and h2_trans)
                    break
        elif http_trans and not tls_trans and not h2_trans:
            while True:
                if not self.random_hostname(url_list):
                    break
        else:
            if self.random_hostname(url_list):
                self.random_tls_ver(not tls_trans and h2_trans)

        if h2_trans and self.tls_ver > 1.1:
            if not tls_trans:
                self.http_ver = 2
            else:
                self.random_http_ver()

        self.session['protocol'] = []
        self.session['protocol'].append({'name': 'http', 'version': self.http_ver})

        if self.tls_ver > 0:
            self.session['protocol'].append(
                {'name': 'tls', 'version': self.tls_vers[self.tls_ver], 'sni': self.hostname,
                 'proxy-verify-mode': 0, 'proxy-provided-cert': True})

        self.session['protocol'].append({'name': 'tcp'})

        self.random_ip_ver()
        self.session['protocol'].append({'name': 'ip', 'version': self.ip_ver})

        self.session['connection-time'] = int(datetime.datetime.utcnow().timestamp() * 1000000000)

        for t in range(transaction_num):
            self.transactions.append(self.random_transaction())

        self.session['transactions'] = self.transactions
        return

    def random_hostname(self, url_list):
        self.url = random.choice(url_list)
        self.hostname, self.path, is_tls = self.get_hostname_from_url(self.url)
        return is_tls

    def random_tls_ver(self, h2_only):
        if h2_only:
            self.tls_ver = random.choice([1.2, 1.3])
        else:
            self.tls_ver = random.choice([1.1, 1.2, 1.3])
        return

    def random_http_ver(self):
        self.http_ver = random.choice([1.1, 2])
        return

    def random_ip_ver(self):
        self.ip_ver = random.choice([4, 6])
        return

    def random_transaction(self):
        new_uuid = uuid.uuid4().hex
        new_uuid = new_uuid[:8] + '-' + new_uuid[8:12] + '-' + \
            new_uuid[12:16] + '-' + new_uuid[16:20] + '-' + new_uuid[20:]

        transaction = {}
        transaction['client-request'] = {}

        request_method = random.choice(['GET', 'POST'])
        request_size = random.randint(1, 1000) if request_method != 'GET' else 0

        if self.http_ver == 1.1:
            transaction['client-request']['method'] = request_method
            transaction['client-request']['scheme'] = 'https' if self.tls_ver > 0 else 'http'
            transaction['client-request']['url'] = self.path
            transaction['client-request']['version'] = str(self.http_ver)

            req_headers = {}
            req_headers['fields'] = []
            req_headers['fields'].append(['Host', self.hostname])
        else:
            req_headers = {}
            req_headers['fields'] = []
            req_headers['fields'].append([':method', request_method])
            req_headers['fields'].append([':scheme', 'https' if self.tls_ver > 0 else 'http'])
            req_headers['fields'].append([':authority', self.hostname])
            req_headers['fields'].append([':path', self.path])

        if request_method == 'POST':
            req_headers['fields'].append(['Content-Type', 'test/html'])
            req_headers['fields'].append(['Content-Length', request_size])

        req_headers['fields'].append(['uuid', new_uuid])

        if has_yaml:
            for i, field in enumerate(req_headers['fields']):
                req_headers['fields'][i] = flow_style_list(field)

        transaction['client-request']['headers'] = req_headers

        transaction['client-request']['content'] = {}
        transaction['client-request']['content']['encoding'] = 'plain'
        transaction['client-request']['content']['size'] = request_size

        # transaction['proxy-request'] = copy.deepcopy(transaction['client-request'])

        transaction['server-response'] = {}

        response_status = random.choice([200, 404])
        response_size = random.randint(1, 1000)

        if self.http_ver == 1.1:
            transaction['server-response']['status'] = response_status
            transaction['server-response']['reason'] = http_status_codes[response_status]

            res_headers = {}
            res_headers['fields'] = []
            if random.choices([1, 2]) == 1:
                res_headers['fields'].append(['Transfer-Encoding', 'chunked'])
            res_headers['fields'].append(['Connection', random.choices(
                ['close', 'keep-alive'], weights=[1, 10], k=1)[0]])
        else:
            res_headers = {}
            res_headers['fields'] = []
            res_headers['fields'].append([':status', response_status])

        res_headers['fields'].append(['Content-Type', 'text/html'])
        res_headers['fields'].append(['Content-Length', response_size])

        if has_yaml:
            for i, field in enumerate(res_headers['fields']):
                res_headers['fields'][i] = flow_style_list(field)

        transaction['server-response']['headers'] = res_headers

        transaction['server-response']['content'] = {}
        transaction['server-response']['content']['encoding'] = 'plain'
        transaction['server-response']['content']['size'] = response_size

        transaction['proxy-response'] = {}
        transaction['proxy-response']['status'] = response_status
        transaction['proxy-response']['reason'] = http_status_codes[response_status]

        # transaction['proxy-response'] = copy.deepcopy(transaction['server-response'])
        return transaction

    @staticmethod
    def get_hostname_from_url(url):
        parsed = urlparse(url)
        is_tls = True if parsed.scheme == "https" else False
        return parsed.netloc, parsed.path, is_tls


class RepalyFile:

    def __init__(self, f_name):
        self.f_name = f_name
        self.replay_file = {}
        self.replay_file['meta'] = {}
        self.replay_file['meta']['version'] = '1.0'
        self.replay_file['sessions'] = []
        self.sess_count = 0
        self.trans_count = 0

    def random_populate(
            self,
            curr_trans_num,
            total_trans_num,
            url_list,
            sess_lower,
            sess_upper,
            trans_lower,
            trans_upper,
            http_trans,
            tls_trans,
            h2_trans):
        sess_num = random.randint(sess_lower, sess_upper)

        for sess in range(sess_num):
            if curr_trans_num + self.trans_count + trans_upper <= total_trans_num:
                trans_num = random.randint(trans_lower, trans_upper)
            else:
                trans_num = total_trans_num - (curr_trans_num + self.trans_count)

            self.trans_count += trans_num

            session = ReplaySession()
            session.random_populate(trans_num, url_list, http_trans, tls_trans, h2_trans)
            self.replay_file['sessions'].append(session.session)

            if total_trans_num == curr_trans_num + self.trans_count:
                self.sess_count = sess + 1
                return self.trans_count, True

        self.sess_count = sess_num
        return self.trans_count, False

    def dump_to_disk(self, print_info, out_json):
        with open(self.f_name, 'w') as out_file:
            if out_json:
                out_file.write(json.dumps(self.replay_file, indent=2))
            else:
                yaml.dump(self.replay_file, out_file)

        if print_info:
            print(
                f'Generated file {self.f_name}, with {self.sess_count} sessions and {self.trans_count} transactions.')

        return


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--number', dest='number', type=int, required=True,
                        help='Number of total transactions.')
    parser.add_argument('-tl', '--trans-lower', dest='trans_lower', type=int, default=10,
                        help='The lower limit of transactions per session.')
    parser.add_argument('-tu', '--trans-upper', dest='trans_upper', type=int, default=10,
                        help='The upper limit of transactions per session.')
    parser.add_argument('-sl', '--sess-lower', dest='sess_lower', type=int, default=10,
                        help='The lower limit of sessions per file.')
    parser.add_argument('-su', '--sess-upper', dest='sess_upper', type=int, default=10,
                        help='The upper limit of sessions per file.')
    parser.add_argument(
        '-tp',
        '--trans-protocols',
        dest='trans_protocols',
        type=str,
        default='all',
        help='A comma separated list of protocols that are allowed to be generated. '
        'Available options are: http, tls, h2, all.')
    parser.add_argument(
        '-u',
        '--url-file',
        dest='url_file',
        type=argparse.FileType('r'),
        required=True,
        help='Path to a file with the list of URLs that can be used.')
    parser.add_argument('-o', '--output', dest='output', type=str, default='replay',
                        help='Path to a directory where the replay files are generated.')
    parser.add_argument('-p', '--prefix', dest='prefix', type=str, default='',
                        help='Prefix for the replay file names.')
    parser.add_argument(
        '-j',
        '--out-json',
        dest='out_json',
        default=False,
        action='store_true',
        help='Dump replay files in JSON format. By default replay files will be formatted as YAML.')
    return parser.parse_args()


def main():
    args = parse_args()

    out_json = (not has_yaml) or args.out_json

    http_trans = False
    tls_trans = False
    h2_trans = False
    trans_protocols = list(map(str.lower, map(str.strip, args.trans_protocols.split(','))))
    for p in trans_protocols:
        if p == 'http':
            http_trans = True
        elif p == 'tls':
            tls_trans = True
        elif p == 'h2':
            h2_trans = True
        elif p == 'all':
            http_trans = True
            tls_trans = True
            h2_trans = True
        else:
            print(f'Invalid protocol value {p}, ignoring...')

    if not http_trans and not tls_trans and not h2_trans:
        all_protocols = input(
            'No valid protocols provided, generate with ALL protocols allowed? [y/N]: ')
        if all_protocols.lower() == 'y':
            http_trans = True
            tls_trans = True
            h2_trans = True
        else:
            print('Please check the help message "python3 replay_gen.py -h/--help".')
            exit(1)

    if pathlib.Path(args.output).is_file():
        print('Output path must be a directory.')
        return 1
    if pathlib.Path(args.output).exists():
        delete_dir = input('Output path already exists, DELETE the directory? [y/N]: ')
        if delete_dir.lower() == 'y':
            shutil.rmtree(args.output)
        else:
            print('Please select a new output path.')
            return 1
    pathlib.Path(args.output).mkdir(parents=True, exist_ok=True)

    # avoid the newlines from readlines()
    url_list = args.url_file.read().splitlines()
    args.url_file.close()

    curr_trans_num = 0
    file_count = 0

    random.seed()

    while True:
        prefix = f'{args.prefix}_' if args.prefix else ''
        suffix = 'json' if out_json else 'yaml'
        f_name = pathlib.PurePath(args.output).joinpath(f'{prefix}{file_count}.{suffix}')

        replay_file = RepalyFile(f_name)
        trans_count, finished = replay_file.random_populate(
            curr_trans_num=curr_trans_num,
            total_trans_num=args.number,
            url_list=url_list,
            sess_lower=args.sess_lower,
            sess_upper=args.sess_upper,
            trans_lower=args.trans_lower,
            trans_upper=args.trans_upper,
            http_trans=http_trans,
            h2_trans=h2_trans,
            tls_trans=tls_trans
        )
        curr_trans_num += trans_count
        replay_file.dump_to_disk(True, out_json)
        file_count += 1

        if finished:
            break

    return 0


if __name__ == '__main__':
    sys.exit(main())
