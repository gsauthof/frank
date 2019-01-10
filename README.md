This repository contains the command line program `frank` for buying
postage online.

The program supports the Deutsche Post service ('INTERNETMARKE'
a.k.a. '1C4A' a.k.a.  OneClickApplikation-Webservice) for letters
and small packages.  It uses the [Python `inema` package][1] for
communicating with that web-service (which uses a custom
[SOAP][2] flavour).

Since mid 2017 it is [integrated with the inema package][1]. That
means you can easily get `frank` via pip, e.g.:

    $ pip3 install --user inema

Thus, this repository is the upstream development repository for
`frank`.

2016, Georg Sauthoff <mail@georg.so>, GPLv3+

## Examples

List all formats that have a height of 297 mm:

    $ frank --list-formats x297

List all products that are called 'sendung' or so:

    $ frank --list-products sendung

Preview a Büchersendung stamp (creates `postage_YYYY-MM-DD.pdf`):

    $ frank --preview --product 78 --format 1

Frank and buy 2 stamps (create 2 page document `postage_YYYY-MM-DD.pdf`):

    $ frank ---format 26  --product 79 'Joe User;Street 1;12345 City' \\
       'Jane User;Fakestreet 2;67890 Fakestadt'

It's also fine to delimit the recipient lines with newline characters.

## Setup

The program `frank` looks for system wide and user specific
config files that include account and default address
information.

For using the Deutsche Post webservice you need 2 things: a
'Portokasse' account (easy) and API credentials (tedious).

You can create a 'Portokasse', i.e. a pre-paid account, as  [part
of creating][4] an [efiliale][3] account. The 'Portokasse' can then
be charged via bank transfer ('Lastschrift') or other means.
Alternatively, you can also [just register a 'Portokasse' account][6] ([see also][5]).

The API credentials have to be requested separately. Basically
you have to fill out some [web-form][5], you get contacted by an
operator for confirmation and then you have to follow-up with a
request for the credentials. Or, you can [directly write an
email][1] to the address of the Deutsche-Post web-service team.

Example of a local `~/.config/frank.conf`:

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


## Background

The [WSDL file of the Deutsche Post webservice][7] is publicly
available. Other service documentation is only available [on
request][5].

The webservice uses SOAP over HTTPS and implements a custom
signing procedure for some headers. Basically the API key is not
send as-is, instead the first 8 characters of the MD5 hash of the
concatenation of API id, timestamp and key are send as signature
(along the API id and timestamp in the clear). Each SOAP request
must include this custom header.

This doesn't make much sense from a technical point of view,
because the service already uses HTTPS, thus this weak signature
mechanism doesn't improve the already established level of
security.

It looks like the purpose of this mechanism is to make the key
extraction a little bit harder for a local user who is able to
add a private CA certificate and use a MITM-proxy on the service
connection. This shouldn't be too effective, though, since the
key still has to be accessed by any program that talks to
the webservice.

See also:

- [python-inema: Python module implementing Deutsche Post 1C4A Internetmarke API][8] (Harlad Welte, 2016-07-23)

## License

The `frank` program is licensed under the GPL v3 or later.


[1]: https://pypi.python.org/pypi/inema
[2]: http://harmful.cat-v.org/software/xml/soap/simple
[3]: https://www.efiliale.de/
[4]: https://www.efiliale.de/efiliale/infocenter/payShipInfo.jsp?tid=sv09_02#paymentinfos
[5]: https://www.deutschepost.de/de/i/internetmarke-porto-drucken/partner-werden.html
[6]: https://portokasse.deutschepost.de/portokasse/#/register/
[7]: https://internetmarke.deutschepost.de/OneClickForAppV3/OneClickForAppServiceV3?wsdl
[8]: http://laforge.gnumonks.org/blog/20160724-python_inema/
