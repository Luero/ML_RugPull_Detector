# RugPull detector

## TODO: some general description

## Guide to files and directories
### - 'data': contains different versions of the dataset in .xlsx format
### - 'data/SOURCE CODE': contains source code for all projects in .txt files (named in line with dataset row numbers)
### - 'TM-RugPull initial analysis': Jupyter notebook with analysis of the original TM-RugPull dataset, contains experiments with data pre-processing and data visualisation
### - 'General pipeline for experimentations': Jupyter notebook with general pre-processing pipeline relevant for all dataset versions except the original. It cleans and transrorms data and trains candidate models. Switching between filenames allows to experiment with different versions and then compare results
### - 'prepare_dataset_for_enrichment': a program that receives original dataset file in .xlxs format as an input and returns its clean version without under-represented blockchains and with extracted contract addresses. It also informs about projects with missing contract addresses and about duplicates
