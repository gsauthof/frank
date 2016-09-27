#!/usr/bin/env python3

# 2016, Georg Sauthoff <mail@georg.so>, GPLv3+

import argparse
import configparser
import os
import sys
import logging
import re
import datetime
import requests

import inema

class Fake_IM(object):

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

try:
  import colorlog
  have_colorlog = True
except ImportError:
  have_colorlog = False

log_format    = '%(asctime)s - %(levelname)-8s - %(message)s'
log_date_format = '%Y-%m-%d %H:%M:%S'

def mk_formatter():
  f = logging.Formatter(log_format, log_date_format)
  return f

def mk_logger():
  log = logging.getLogger()
  log.setLevel(logging.DEBUG)

  if have_colorlog:
    cformat   = '%(log_color)s' + log_format
    cf = colorlog.ColoredFormatter(cformat, log_date_format,
      log_colors = { 'DEBUG': 'reset', 'INFO': 'reset',
        'WARNING' : 'bold_yellow' , 'ERROR': 'bold_red',
        'CRITICAL': 'bold_red'})

  else:
    cf = mk_formatter()

  ch = logging.StreamHandler()
  ch.setLevel(logging.WARNING)
  if os.isatty(2):
    ch.setFormatter(cf)
  else:
    ch.setFormatter(f)
  log.addHandler(ch)

  return logging.getLogger(__name__)

log = mk_logger()

def setup_file_logging(filename):
  log = logging.getLogger()
  fh = logging.FileHandler(filename)
  fh.setLevel(logging.DEBUG)
  f = logging.Formatter(log_format + ' - [%(name)s]', log_date_format)
  fh.setFormatter(f)
  log.addHandler(fh)


def mk_arg_parser():
  p = argparse.ArgumentParser(
      formatter_class=argparse.RawDescriptionHelpFormatter,
      description='buy postage online',
      epilog='''Currenty, the program only supports the Deutsche Post
service for letters and small packages.

Account details are read from a config file, by default this is
~/.config/frank.conf. See the README.md for an example.

Examples:

List all formats that have a height of 297 mm:

    $ frank --list-formats x297

List all products that are called 'sendung' or so:

   $ frank --list-products sendung

Preview a Büchersendung stamp (creates postage_YYYY-MM-DD.pdf):

   $ frank --preview --product 78 --format 1

Frank and buy 2 stamps (create 2 page document postage_YYYY-MM-DD.pdf):

   $ frank ---format 26  --product 79 'Joe User;Street 1;12345 City' \\
       'Jane User;Fakestreet 2;67890 Fakestadt'

2016, Georg Sauthoff <mail@georg.so>, GPLv3+

'''
      )
  p.add_argument('recipients', metavar='RECIPIENT', nargs='*',
      help = 'recipients')
  p.add_argument('--config', action='append',
      metavar='FILENAME', help='user specific config file')
  p.add_argument('--debug', help='store debug message into log file')
  p.add_argument('--dry', action='store_true', help='dry run')
  p.add_argument('--format' ,'-f', default='1',
      help='format id for the resulting pdf')
  p.add_argument('--global-conf', default = '/usr/share/frank/frank.conf',
      metavar='FILENAME', help='global config file')
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
  return p

def parse_args(xs = None):
  arg_parser = mk_arg_parser()
  if xs or xs == []:
    args = arg_parser.parse_args(xs)
  else:
    args = arg_parser.parse_args()
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
  for k,v in inema.inema.marke_products.items():
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
  for f in inema.inema.formats:
    if e.search(f['name']) or e.search(f['pageType']) \
        or e.search('{}x{}'.format(f['pageLayout']['size']['x'],
                                   f['pageLayout']['size']['y'])):
      print(fs.format(f['id'], f['name'], f['pageLayout']['size']['x'],
          f['pageLayout']['size']['y'],
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

def parse_addresses(args, conf):
  recipients = []
  for r in args.recipients:
    recipients.append(parse_address(r, conf))
  args.recipients = recipients
  sender = []
  for r in args.sender:
    sender.append(parse_address(r, conf))
  args.sender = sender
  if not args.manifest and conf.has_section('general'):
    args.manifest = conf['general'].get('manifest', False)
  return args

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
    with open(filename, 'wb') as f:
      f.write(pdf_bin)

def get_format(ident):
  for f in inema.inema.formats:
    if f['id'] == int(ident):
      return f
  raise ValueError("Couldn't find format id: {}".format(ident))

def get_page_info(f):
  return ( int(f['pageLayout']['labelCount']['labelX']),
           int(f['pageLayout']['labelCount']['labelY']) )

def run(args, conf):
  if args.list_products:
    list_products(args.list_products)
    return 0
  if args.list_formats:
    list_formats(args.list_formats)
    return 0
  ps = args.product
  ss = args.sender
  if args.dry:
    im = Fake_IM()
  else:
    im = inema.Internetmarke(conf['api']['id'], conf['api']['key'],
        conf['api'].get('key_phase', '1'))
    im.authenticate(conf['account']['user'], conf['account']['password'])
  if args.preview:
    link = im.retrievePreviewPDF(args.product[0], args.format)
    pdf = requests.get(link, stream=True)
    with open(mk_filename(args), 'wb') as f:
      f.write(pdf.content)
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
  log.warn('Buying postage for {} €'.format(im.compute_total()/100))
  res = im.checkoutPDF(args.format)
  store_files(res, args)
  return 0

def main():
  args = parse_args()
  conf = read_config([args.global_conf, args.sys_conf]
    + [os.path.expanduser(x) for x in args.config] )
  args = parse_addresses(args, conf)
  if args.debug:
    setup_file_logging(args.debug)
  return run(args, conf)

if __name__ == '__main__':
  sys.exit(main())

