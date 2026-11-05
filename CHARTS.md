# Getting the charts

Charts live in the folder `../charts/`, next to this repository, so a fresh clone does not include them.

**Our own chart sessions cannot be downloaded.** Nearly everything in that folder was authored here and has no upstream source. Restore it from your own backup of this folder.

**The official Phigros charts can be downloaded** from the community repository [7aGiven/Phigros_Resource](https://github.com/7aGiven/Phigros_Resource). To get every difficulty for every song at the commit this workspace uses:

```sh
curl -L -o phigros-charts.tar.gz https://codeload.github.com/7aGiven/Phigros_Resource/tar.gz/5d40bfdf05bee53f5107a6ea5620ca0e953de815
```

Audio and illustrations are on that repository's `music` and `illustration` branches. To rebuild only the verified IN reference corpus instead:

```sh
python3 research/arrangement-training/acquire_in.py
```

These files are for private reference. Being available does not grant a license to redistribute them.
