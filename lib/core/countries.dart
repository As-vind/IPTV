// Détection du pays d'une chaîne à partir des métadonnées M3U / Xtream.

const Map<String, String> kCountries = {
  'FR': 'France', 'BE': 'Belgique', 'CH': 'Suisse', 'LU': 'Luxembourg', 'CA': 'Canada',
  'US': 'États-Unis', 'GB': 'Royaume-Uni', 'IE': 'Irlande', 'DE': 'Allemagne', 'AT': 'Autriche',
  'IT': 'Italie', 'ES': 'Espagne', 'PT': 'Portugal', 'NL': 'Pays-Bas', 'PL': 'Pologne',
  'RO': 'Roumanie', 'BG': 'Bulgarie', 'GR': 'Grèce', 'TR': 'Turquie', 'RU': 'Russie',
  'UA': 'Ukraine', 'SE': 'Suède', 'NO': 'Norvège', 'DK': 'Danemark', 'FI': 'Finlande',
  'CZ': 'Tchéquie', 'SK': 'Slovaquie', 'HU': 'Hongrie', 'HR': 'Croatie', 'RS': 'Serbie',
  'BA': 'Bosnie', 'SI': 'Slovénie', 'AL': 'Albanie', 'MK': 'Macédoine du Nord',
  'MA': 'Maroc', 'DZ': 'Algérie', 'TN': 'Tunisie', 'EG': 'Égypte', 'SA': 'Arabie saoudite',
  'AE': 'Émirats arabes unis', 'QA': 'Qatar', 'LB': 'Liban', 'IQ': 'Irak', 'IR': 'Iran',
  'IL': 'Israël', 'IN': 'Inde', 'PK': 'Pakistan', 'BD': 'Bangladesh', 'CN': 'Chine',
  'JP': 'Japon', 'KR': 'Corée du Sud', 'TH': 'Thaïlande', 'VN': 'Vietnam', 'PH': 'Philippines',
  'ID': 'Indonésie', 'MY': 'Malaisie', 'AU': 'Australie', 'NZ': 'Nouvelle-Zélande',
  'MX': 'Mexique', 'BR': 'Brésil', 'AR': 'Argentine', 'CL': 'Chili', 'CO': 'Colombie',
  'PE': 'Pérou', 'VE': 'Venezuela', 'SN': 'Sénégal', 'CI': "Côte d'Ivoire", 'CM': 'Cameroun',
  'CD': 'RD Congo', 'ML': 'Mali', 'NG': 'Nigeria', 'GH': 'Ghana', 'ZA': 'Afrique du Sud',
  'HT': 'Haïti', 'MU': 'Maurice', 'RE': 'La Réunion', 'MG': 'Madagascar',
  'ARAB': 'Monde arabe', 'AFR': 'Afrique', 'LAT': 'Amérique latine',
  'EXYU': 'Ex-Yougoslavie', 'INT': 'International', 'ZZ': 'Autres',
};

const Map<String, String> _aliases = {
  'UK': 'GB', 'ENG': 'GB', 'USA': 'US', 'FRA': 'FR', 'BEL': 'BE', 'SUI': 'CH', 'CHE': 'CH',
  'CAN': 'CA', 'QC': 'CA', 'GER': 'DE', 'DEU': 'DE', 'ITA': 'IT', 'ESP': 'ES', 'SPA': 'ES',
  'POR': 'PT', 'PRT': 'PT', 'BRA': 'BR', 'NLD': 'NL', 'HOL': 'NL', 'POL': 'PL', 'ROU': 'RO',
  'ROM': 'RO', 'TUR': 'TR', 'RUS': 'RU', 'UKR': 'UA', 'GRE': 'GR', 'SWE': 'SE', 'NOR': 'NO',
  'DEN': 'DK', 'FIN': 'FI', 'ALB': 'AL', 'MAR': 'MA', 'ALG': 'DZ', 'TUN': 'TN', 'EGY': 'EG',
  'KSA': 'SA', 'UAE': 'AE', 'IND': 'IN', 'PAK': 'PK', 'CHN': 'CN', 'JPN': 'JP', 'KOR': 'KR',
  'MEX': 'MX', 'ARG': 'AR', 'MRI': 'MU', 'MUS': 'MU', 'REU': 'RE',
  'AR': 'ARAB', 'ARB': 'ARAB', 'ARA': 'ARAB', 'ARABIC': 'ARAB',
  'EXYU': 'EXYU', 'YU': 'EXYU', 'LATINO': 'LAT', 'AFRICA': 'AFR', 'AFRIQUE': 'AFR',
};

final Map<String, String> _nameToCode = () {
  final m = <String, String>{};
  kCountries.forEach((c, n) {
    if (c != 'INT' && c != 'ZZ') m[n.toUpperCase()] = c;
  });
  m.addAll(const {
    'FRANCE': 'FR', 'FRENCH': 'FR', 'BELGIUM': 'BE', 'SWITZERLAND': 'CH', 'GERMANY': 'DE',
    'GERMAN': 'DE', 'ITALY': 'IT', 'ITALIAN': 'IT', 'SPAIN': 'ES', 'SPANISH': 'ES',
    'PORTUGAL': 'PT', 'PORTUGUESE': 'PT', 'NETHERLANDS': 'NL', 'DUTCH': 'NL', 'POLAND': 'PL',
    'ROMANIA': 'RO', 'TURKEY': 'TR', 'TURKISH': 'TR', 'RUSSIA': 'RU', 'GREECE': 'GR',
    'SWEDEN': 'SE', 'NORWAY': 'NO', 'DENMARK': 'DK', 'FINLAND': 'FI', 'UNITED STATES': 'US',
    'UNITED KINGDOM': 'GB', 'ENGLAND': 'GB', 'BRAZIL': 'BR', 'MEXICO': 'MX', 'ARGENTINA': 'AR',
    'MOROCCO': 'MA', 'ALGERIA': 'DZ', 'TUNISIA': 'TN', 'EGYPT': 'EG', 'INDIA': 'IN',
    'CHINA': 'CN', 'JAPAN': 'JP', 'KOREA': 'KR', 'QUEBEC': 'CA', 'QUÉBEC': 'CA',
    'ARABIC': 'ARAB', 'ARAB': 'ARAB', 'LATINO': 'LAT', 'AFRICA': 'AFR', 'AFRIQUE': 'AFR',
    'EX-YU': 'EXYU', 'ITALIA': 'IT', 'DEUTSCHLAND': 'DE', 'ESPAÑA': 'ES', 'ESPANA': 'ES',
    'NEDERLAND': 'NL', 'POLSKA': 'PL', 'TÜRKIYE': 'TR', 'TURKIYE': 'TR', 'BRASIL': 'BR',
    'SVERIGE': 'SE', 'NORGE': 'NO', 'DANMARK': 'DK', 'SUOMI': 'FI', 'SCHWEIZ': 'CH',
    'MAGHREB': 'MA', 'USA': 'US', 'UK': 'GB', 'CANADA': 'CA', 'MAURITIUS': 'MU', 'MAURICE': 'MU',
  });
  return m;
}();

final RegExp _nameRe = () {
  final names = _nameToCode.keys.toList()..sort((a, b) => b.length.compareTo(a.length));
  return RegExp('(?<![A-Za-zÀ-ÿ])(${names.map(RegExp.escape).join('|')})(?![A-Za-zÀ-ÿ])');
}();
final RegExp _prefixRe =
    RegExp(r'^[\s|\[\(\{#★•▶\-]*(EX-?YU|LATINO|ARABIC|AFRICA|AFRIQUE|[A-Z]{2,3})(?=\s*[|\]\)\}:\-–»/]|\s|$)');
final RegExp _suffixRe = RegExp(r'(?:^|[\s\(\[|])([A-Z]{2,3})[\)\]|]?\s*$');
final RegExp _tvgRe = RegExp(r'\.([a-z]{2})(?:@|$)');

String? resolveCountry(String tok) {
  var t = tok.toUpperCase().replaceAll('-', '').replaceAll(' ', '');
  t = _aliases[t] ?? t;
  return (kCountries.containsKey(t) && t != 'ZZ') ? t : null;
}

String detectCountry({String group = '', String name = '', String tvgCountry = '', String tvgId = ''}) {
  for (final raw in tvgCountry.split(RegExp(r'[;,|/ ]+'))) {
    var t = raw.trim().toUpperCase();
    if (t == 'UK') t = 'GB';
    if (kCountries.containsKey(t) && t != 'ZZ') return t;
  }
  for (final text in [group, name]) {
    final m = _prefixRe.firstMatch(text);
    if (m != null) {
      final r = resolveCountry(m.group(1)!);
      if (r != null) return r;
    }
  }
  if (tvgId.isNotEmpty) {
    final m = _tvgRe.firstMatch(tvgId.toLowerCase());
    if (m != null) {
      var t = m.group(1)!.toUpperCase();
      if (t == 'UK') t = 'GB';
      if (kCountries.containsKey(t)) return t;
    }
  }
  if (group.isNotEmpty) {
    final m = _nameRe.firstMatch(group.toUpperCase());
    if (m != null) return _nameToCode[m.group(1)!] ?? 'ZZ';
  }
  for (final text in [group, name]) {
    final m = _suffixRe.firstMatch(text);
    if (m != null) {
      final r = resolveCountry(m.group(1)!);
      if (r != null) return r;
    }
  }
  return 'ZZ';
}

String countryName(String code) => kCountries[code] ?? code;
