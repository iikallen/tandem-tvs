# Search language dictionaries

Stage 9 uses separate PostgreSQL search configurations and combines their ranks in the
application query. Russian uses PostgreSQL `pg_catalog.russian`. Kazakh uses the
vendored Hunspell files in `infra/postgres/search/hunspell-kk`; it is never chained to
the Russian dictionary.

## Kazakh provenance

- Upstream: `https://github.com/taem/hunspell-kk`
- Reviewed commit: `86f6eeaa0aea4b41044a191ee5ae6311770d9adb`
- Debian package version reviewed for licensing: `hunspell-kk 1.1.2-2`
- Encoding: UTF-8 (`SET UTF-8` in `kk_KZ.aff`)
- Selected license: Mozilla Public License 1.1 or later, from the upstream
  `GPL-2+ or LGPL-2.1+ or MPL-1.1+` choice
- Copyright and attribution: see `UPSTREAM-COPYRIGHT`

SHA-256:

```text
254293c1c6ae893b87ec5c1fea3b72f696fe7821a3d87740ebad86b780d6e33a  kk_KZ.aff
80090f69c0d098425020ab378084d05ec7a4a90155750faf73742cdde7088012  kk_KZ.dic
fee60a549eb2edecc6c8c80a84852353932a02317881fc4f80888671931e90e5  README_kk_KZ.txt
5bb4535cad3002d8cb3e7a439f6666b0bce1d1f9a41427b5edd60db73ccc1e4f  UPSTREAM-COPYRIGHT
f849fc26a7a99981611a3a370e83078deb617d12a45776d6c4cada4d338be469  LICENSE-MPL-1.1.txt
```

The release gate computes these hashes directly. The authoritative `README.sha256`
beside the files is machine-readable.

## Engineering license review

The dictionary files are offered under three alternatives; this repository elects
MPL-1.1+, retains attribution and keeps the dictionary files identifiable and
replaceable. This is an engineering review, not legal advice. Customer counsel must
approve production redistribution if organizational policy requires it.

The production image copies pinned repository files only. It does not download a
dictionary during build.
