#!/usr/bin/env python3

# 2016, Georg Sauthoff <mail@georg.so>, GPLv3+

import argparse
import configparser
import csv
import datetime
import json
import logging
import os
import re
import requests
import subprocess
import sys
import zeep

# to use a developer version of inema if available
if __name__ == '__main__':
  import inspect
  s = inspect.getsourcefile(lambda:0)
  if s and s != '<stdin>':
    d = os.path.dirname(os.path.abspath(s)) + '/python-inema'
    if os.path.exists(d):
      sys.path.insert(0, d)
  from inema import Internetmarke, inema
else:
  from . import Internetmarke, inema

class Fake_IM:

  def checkoutPDF(self, format_id):
    pass

  def build_addr(self, street, number, code, city, country):
    pass

  def build_pers_addr(self, first, name, address):
    pass

  def build_comp_addr(self, first, name, address):
    pass

  def build_position(self, product, sender, receiver, layout = "AddressZone", pdf = False, x=1, y=1, page=1):
    pass

  def add_position(self, position):
    pass

  def retrievePreviewPDF(self, prod_code, page_format, layout = "AddressZone"):
    pass

  def compute_total(self):
    return 0

try:
  import colorlog
except ImportError:
  pass

log_format    = '%(asctime)s - %(levelname)-8s - %(message)s [%(name)s]'
log_date_format = '%Y-%m-%d %H:%M:%S'

def setup_logging():
  root = logging.getLogger()
  root.setLevel(logging.WARN)
  logging.getLogger(__name__).setLevel(logging.INFO)

  if 'colorlog' in sys.modules and os.isatty(2):
    cformat   = '%(log_color)s' + log_format
    cf = colorlog.ColoredFormatter(cformat, log_date_format,
      log_colors = { 'DEBUG': 'reset', 'INFO': 'reset',
        'WARNING' : 'bold_yellow' , 'ERROR': 'bold_red',
        'CRITICAL': 'bold_red'})

  else:
    cf = logging.Formatter(log_format, log_date_format)

  ch = logging.StreamHandler()
  ch.setFormatter(cf)
  root.addHandler(ch)

log = logging.getLogger(__name__)

def setup_file_logging(filename):
  root = logging.getLogger()
  root.setLevel(logging.DEBUG)
  logging.getLogger(__name__).setLevel(logging.NOTSET)

  fh = logging.FileHandler(filename)
  fh.setLevel(logging.DEBUG)
  f = logging.Formatter(log_format, log_date_format)
  fh.setFormatter(f)
  root.addHandler(fh)

  class Filter:
    def filter(self, r):
      return r.name == __name__ or r.levelno >= logging.WARNING

  ch = root.handlers[0]
  ch.setLevel(logging.INFO)
  ch.addFilter(Filter())



def mk_arg_parser():
  p = argparse.ArgumentParser(
      formatter_class=argparse.RawDescriptionHelpFormatter,
      description='buy postage online',
      epilog='''The program interfaces with the Deutsche Post
postage service for letters and small packages.

Account details are read from a config file, by default this is
~/.config/frank.conf. An example config:

    [api]
    id = your-partner-id
    key = your-api-key
    key_phase = 1

    [account]
    user = portokasse-user
    password = portokasse-pw

    [a.default]
    first =
    name = Firma ACME
    street = Lindenallee
    number = 3
    zip = 12345
    city = Bielefeld

Examples:

List all formats that have a height of 297 mm:

    $ frank --list-formats x297

List all products that are called 'sendung' or so:

   $ frank --list-products sendung

Preview a Büchersendung stamp (creates postage_YYYY-MM-DD.pdf):

   $ frank --preview --product 78 --format 1

Frank and buy 2 stamps (creates 2 page document postage_YYYY-MM-DD.pdf):

   $ frank ---format 26  --product 79 'Joe User;Street 1;12345 City' \\
       'Jane User;Fakestreet 2;67890 Fakestadt'

It's also fine to delimit the recipient lines with newline characters.

2016, Georg Sauthoff <mail@georg.so>, GPLv3+

'''
      )
  p.add_argument('recipients', metavar='RECIPIENT', nargs='*',
      help = 'recipients')
  p.add_argument('--config', action='append',
      metavar='FILENAME', help='user specific config file')
  p.add_argument('--csv', metavar='FILENAME',
      help='read recipient data from CSV file (1st row is header)')
  p.add_argument('--debug', help='store debug message into log file')
  p.add_argument('--dry', action='store_true', help='dry run')
  p.add_argument('--format' ,'-f', default='1',
      help='format id for the resulting pdf')
  p.add_argument('--global-conf', default = '/usr/share/frank/frank.conf',
      metavar='FILENAME', help='global config file')
  p.add_argument('--json', action='store_true',
      help='print tablses as json')
  p.add_argument('--list-formats', nargs='?', default=None, const='.',
      metavar='REGEX', help='list available formats')
  p.add_argument('--list-products', nargs='?', default=None, const='.',
      metavar='REGEX', help='list available products')
  p.add_argument('--manifest', action='store_true',
      help='write manifest pdf')
  p.add_argument('--output', '-o', default='.', metavar='DIRECTORY',
      help='output directory where postage files are created')
  p.add_argument('--preview', action='store_true',
      help='only retrieve preview documents')
  p.add_argument('--product' ,'-p', action='append',
      help='product id(s) to use for the recipient(s)')
  p.add_argument('--sender', action='append', help='sender(s)')
  p.add_argument('--suffix', default='', help='postage basename suffix')
  p.add_argument('--sys-conf', default = '/etc/frank.conf',
      metavar='FILENAME', help='machine specific config file')
  p.add_argument('--update', action='store_true',
      help='update internal format list via webservice')
  p.add_argument('--print', action='store_true', default=False,
      help='Print the retrieved PDF with the lpr command')
  return p

def parse_args(*xs):
  arg_parser = mk_arg_parser()
  args = arg_parser.parse_args(*xs)

  if args.debug:
    setup_file_logging(args.debug)
  if not args.config:
    args.config = [ '~/.config/frank.conf' ]
  if not args.format:
    args.format = ['26']
  if not args.sender:
    args.sender = ['$default']
  return args

def read_config(filenames):
  c = configparser.ConfigParser()
  c.read(filenames)
  return c

def list_products(expr):
  l = []
  e = re.compile(expr, flags=re.IGNORECASE)
  for k,v in inema.marke_products.items():
    if not e.search(v['name']):
      continue
    h = v
    h['id'] = int(k)
    if not h['max_weight']:
      h['max_weight'] = ''
    s = h['cost_price']
    t = s.split('.')
    if t.__len__() == 1:
      h['cost_price'] = s + ' ' * 3
    else:
      h['cost_price'] = s + ' ' * (2 - t[1].__len__())
    l.append(h)
  l.sort(key=lambda h : h['id'])
  fs = '{:>6} {:<70} {:>6} {:>6} {:>5}'
  print(fs.format('id', 'name', 'EUR', 'g', 'intl'))
  print('-'*(6+70+6+6+5 +4))
  for h in l:
    print(fs.format(h['id'], h['name'], h['cost_price'], h['max_weight'],
      h['international']))

def list_formats(expr):
  e = re.compile(expr, flags=re.IGNORECASE)
  fs = '{:>6} {:<44} {:>3}*{:>3} {:>5} {:<12} {:>3} {:>3}'
  print(fs.format('id', 'name', 'w', 'h', '#ls', 'type', 'adr', 'img'))
  print('-'*(6+44+3+3+5+12+3+3 +7))
  for f in inema.formats:
    if e.search(f['name']) or e.search(f['pageType']) \
        or e.search('{}x{}'.format(f['pageLayout']['size']['x'],
                                   f['pageLayout']['size']['y'])):
      print(fs.format(f['id'], f['name'], int(f['pageLayout']['size']['x']),
          int(f['pageLayout']['size']['y']),
           int(f['pageLayout']['labelCount']['labelX'])
          *int(f['pageLayout']['labelCount']['labelY']), f['pageType'],
          f['isAddressPossible'], f['isImagePossible']) )

def parse_address(s, conf):
  if s.startswith('$'):
    h = conf['a.'+s[1:]]
    return ( h.get('first', ''), h['name'], h['street'], h['number'],
        h['zip'], h['city'], h.get('country', 'DEU') )
  delimiter = None
  for d in ['\n', ';']:
    if d in s:
      delimiter = d
  if not delimiter:
    raise ValueError('recipient string has no known delimiters')
  first = ''; name = ''; street = ''; number = ''; zipcode = ''; city = ''
  country = 'DEU'
  l = s.split(delimiter)
  if l.__len__() > 0:
    xs = l[0].split(' ')
    if xs.__len__() == 1:
      first = ''
      name = xs[0]
    else:
      first = ' '.join(xs[0:-1])
      name = xs[-1]
  if l.__len__() > 1:
    xs = l[1].split(' ')
    if xs.__len__() == 1:
      street = xs[0]
      number = ''
    else:
      street = ' '.join(xs[0:-1])
      number = xs[-1]
  if l.__len__() > 2:
    xs = l[2].split(' ')
    if xs.__len__() == 1:
      zipcode = ''
      city = xs[0]
    else:
      zipcode = xs[0]
      city = ' '.join(xs[1:])
  if l.__len__() > 3:
    c = l[3].strip()
    if c:
      country = c
  return (first, name, street, number, zipcode, city, country)

def parse_csv(filename):
  xs = []
  ps = []
  with open(filename, 'r') as f:
    rs = csv.reader(f)
    next(rs)
    for r in rs:
      xs.append(r[0:7] + ['']*(7-r.__len__()))
      if r.__len__() > 7:
        ps.append(r[7])
  return (xs, ps)


def parse_addresses(args, conf):
  recipients = []
  for r in args.recipients:
    recipients.append(parse_address(r, conf))
  args.recipients = recipients
  sender = []
  for r in args.sender:
    sender.append(parse_address(r, conf))
  args.sender = sender
  if args.csv:
    t = parse_csv(args.csv)
    args.recipients = args.recipients + t[0]
    if not args.product:
      args.product = []
    args.product = args.product + t[1]

def apply_config(args, conf):
  if not args.manifest and conf.has_section('general'):
    args.manifest = conf['general'].get('manifest', False)

def mk_address(im, x, conf):
  a = im.build_addr(x[-5], x[-4], x[-3], x[-2], x[-1])
  if x[0]:
    r = im.build_pers_addr(x[0], x[1], a)
  else:
    r = im.build_comp_addr(x[1], a)
  return r;

def buy(im, sender, recipient, product, i, pi, args, conf):
  src = mk_address(im, sender, conf)
  dst = mk_address(im, recipient, conf)
  page   = int(i / (pi[0] * pi[1])) + 1
  column = int(i % pi[0]) + 1
  row    = int(int(i / pi[0]) % pi[1]) + 1
  p = im.build_position(product, src, dst, pdf=True,
      page=page, x=column, y=row)
  im.add_position(p)


def mk_filename(args, base='postage'):
  filename = '{}/{}_{}{}.pdf'.format(args.output, base,
      datetime.datetime.now().strftime('%Y-%m-%d'), args.suffix)
  return filename

def store_files(res, args):
  if hasattr(res, 'manifest_pdf_bin') and args.manifest:
    with open(mk_filename(base='manifest'), 'wb') as f:
      f.write(res.manifest_pdf_bin)
  i = 1
  pdf_bin = None
  if hasattr(res, 'pdf_bin'):
    pdf_bin = res.pdf_bin
  elif hasattr(res.shoppingCart.voucherList.voucher[0], 'pdf_bin'):
    pdf_bin = res.shoppingCart.voucherList.voucher[0].pdf_bin
  if pdf_bin:
    filename = mk_filename(args)
    log.info('Writing: {}'.format(filename))
    with open(filename, 'wb') as f:
      f.write(pdf_bin)
    if args.print:
      log.info('Printing: {}'.format(filename))
      subprocess.check_call(['lpr', filename])

def get_format(ident):
  for f in inema.formats:
    if f['id'] == int(ident):
      return f
  raise ValueError("Couldn't find format id: {}".format(ident))

def get_page_info(f):
  return ( int(f['pageLayout']['labelCount']['labelX']),
           int(f['pageLayout']['labelCount']['labelY']) )

def do_list_products(args):
  if args.list_products:
    list_products(args.list_products)
    return True

def do_list_formats(args):
  if args.list_formats:
    if args.json:
      print(json.dumps(inema.formats, indent=2))
    else:
      list_formats(args.list_formats)
    return True

def do_update_list_formats(im, args):
  if args.list_formats and args.update:
    inema.formats = sorted(zeep.helpers.serialize_object(
      im.retrievePageFormats()), key=lambda x:x['id'])
    return do_list_formats(args)

def do_create_preview(im, args):
  if args.preview:
    link = im.retrievePreviewPDF(args.product[0], args.format)
    pdf = requests.get(link, stream=True)
    with open(mk_filename(args), 'wb') as f:
      f.write(pdf.content)
    return True

def run(args, conf):
  if do_list_products(args):
    return 0
  if not args.update and do_list_formats(args):
    return 0
  ps = args.product
  ss = args.sender
  if args.dry:
    im = Fake_IM()
  else:
    im = Internetmarke(conf['api']['id'], conf['api']['key'],
        conf['api'].get('key_phase', '1'))
    im.authenticate(conf['account']['user'], conf['account']['password'])
  if do_create_preview(im, args):
    return 0
  if do_update_list_formats(im, args):
    return 0
  page = get_page_info(get_format(args.format))
  i = 0
  for r in args.recipients:
    buy(im, ss[0], r, ps[0], i, page, args, conf)
    if ps.__len__() > 1:
      ps = ps[1:]
    if ss.__len__() > 1:
      ss = ss[1:]
    i = i + 1
  log.warning('Buying postage for {} €'.format(im.compute_total()/100))
  res = im.checkoutPDF(args.format)
  store_files(res, args)
  return 0

def imain(args):
  conf = read_config([args.global_conf, args.sys_conf]
    + [os.path.expanduser(x) for x in args.config] )
  parse_addresses(args, conf)
  apply_config(args, conf)
  try:
    return run(args, conf)
  except zeep.exceptions.Fault as e:
    d = str(e.detail)
    try:
      d = zeep.wsdl.utils.etree_to_string(e.detail).decode()
      ids = e.detail.xpath('//*[name()="id"]')
      ms = e.detail.xpath('//*[name()="message"]')
      d = " - ".join(", ".join(x.text for x in xs) for xs in (ids, ms))
    except TypeError:
      pass
    log.error('{} ({})'.format(e.message, d))
    return 1

def main():
  setup_logging()
  args = parse_args()
  log.debug('Starting frank.py')
  return imain(args)

if __name__ == '__main__':
  sys.exit(main())

