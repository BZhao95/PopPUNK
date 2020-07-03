#!/usr/bin/env python
# vim: set fileencoding=<utf-8> :
# Copyright 2018-2020 John Lees and Nick Croucher

# universal
import os
import sys
# additional
import numpy as np
import networkx as nx
import subprocess

# required from v2.1.1 onwards (no mash support)
import pp_sketchlib

# import poppunk package
from .__init__ import __version__

from .models import *

from .sketchlib import no_sketchlib, checkSketchlibLibrary

from .lineage_clustering import cluster_into_lineages

from .network import fetchNetwork
from .network import constructNetwork
from .network import extractReferences
from .network import writeDummyReferences
from .network import addQueryToNetwork
from .network import printClusters

from .plot import outputsForMicroreact
from .plot import outputsForCytoscape
from .plot import outputsForPhandango
from .plot import outputsForGrapetree

from .prune_db import prune_distance_matrix

from .sketchlib import calculateQueryQueryDistances

from .utils import setupDBFuncs
from .utils import storePickle
from .utils import readPickle
from .utils import writeTmpFile
from .utils import qcDistMat
from .utils import update_distance_matrices
from .utils import readRfile
from .utils import readIsolateTypeFromCsv

# Minimum sketchlib version
SKETCHLIB_MAJOR = 1
SKETCHLIB_MINOR = 4

#******************************#
#*                            *#
#* Command line parsing       *#
#*                            *#
#******************************#
def get_options():

    import argparse

    parser = argparse.ArgumentParser(description='PopPUNK (POPulation Partitioning Using Nucleotide Kmers)',
                                     prog='PopPUNK')

    modeGroup = parser.add_argument_group('Mode of operation')
    mode = modeGroup.add_mutually_exclusive_group(required=True)
    mode.add_argument('--easy-run',
            help='Create clusters from assemblies with default settings',
            default=False,
            action='store_true')
    mode.add_argument('--create-db',
            help='Create pairwise distances database between reference sequences',
            default=False,
            action='store_true')
    mode.add_argument('--fit-model',
            help='Fit a mixture model to a reference database',
            default=False,
            action='store_true')
    mode.add_argument('--refine-model',
            help='Refine the accuracy of a fitted model',
            default=False,
            action='store_true')
    mode.add_argument('--assign-query',
            help='Assign the cluster of query sequences without re-running the whole mixture model',
            default=False,
            action='store_true')
    mode.add_argument('--generate-viz',
            help='Generate files for a visualisation from an existing database',
            default=False,
            action='store_true')
    mode.add_argument('--threshold',
            help='Create model at this core distance threshold',
            default=None,
            type=float)
    mode.add_argument('--lineage-clustering',
            help='Identify lineages within a strain',
            default=False,
            action='store_true')
    mode.add_argument('--assign-lineages',
            help='Assign isolates to an existing lineages scheme',
            default=False,
            action='store_true')
    mode.add_argument('--use-model',
            help='Apply a fitted model to a reference database to restore database files',
            default=False,
            action='store_true')


    # input options
    iGroup = parser.add_argument_group('Input files')
    iGroup.add_argument('--ref-db',type = str, help='Location of built reference database')
    iGroup.add_argument('--r-files', help='File listing reference input assemblies')
    iGroup.add_argument('--q-files', help='File listing query input assemblies')
    iGroup.add_argument('--distances', help='Prefix of input pickle of pre-calculated distances')
    iGroup.add_argument('--external-clustering', help='File with cluster definitions or other labels '
                                                      'generated with any other method.', default=None)
    iGroup.add_argument('--viz-lineages', help='CSV with lineage definitions to use for visualisation'
                                                    'rather than strain definitions.', default=None)

    # output options
    oGroup = parser.add_argument_group('Output options')
    oGroup.add_argument('--output', required=True, help='Prefix for output files (required)')
    oGroup.add_argument('--plot-fit', help='Create this many plots of some fits relating k-mer to core/accessory distances '
                                            '[default = 0]', default=0, type=int)
    oGroup.add_argument('--full-db', help='Keep full reference database, not just representatives', default=False, action='store_true')
    oGroup.add_argument('--update-db', help='Update reference database with query sequences', default=False, action='store_true')
    oGroup.add_argument('--overwrite', help='Overwrite any existing database files', default=False, action='store_true')

    # comparison metrics
    kmerGroup = parser.add_argument_group('Kmer comparison options')
    kmerGroup.add_argument('--min-k', default = 13, type=int, help='Minimum kmer length [default = 9]')
    kmerGroup.add_argument('--max-k', default = 29, type=int, help='Maximum kmer length [default = 29]')
    kmerGroup.add_argument('--k-step', default = 4, type=int, help='K-mer step size [default = 4]')
    kmerGroup.add_argument('--sketch-size', default=10000, type=int, help='Kmer sketch size [default = 10000]')
    kmerGroup.add_argument('--min-kmer-count', default=0, type=int, help='Minimum k-mer count when using reads as input [default = 0]')
    kmerGroup.add_argument('--exact-count', default=False, action='store_true',
                           help='Use the exact k-mer counter with reads '
                                '[default = use countmin counter]')
    kmerGroup.add_argument('--strand-preserved', default=False, action='store_true',
                           help='Treat input as being on the same strand, and ignore reverse complement '
                                'k-mers [default = use canonical k-mers]')

    # qc options
    qcGroup = parser.add_argument_group('Quality control options')
    qcGroup.add_argument('--max-a-dist', default = 0.5, type=float, help='Maximum accessory distance to permit '
                                                                         '[default = 0.5]')
    qcGroup.add_argument('--ignore-length', help='Ignore outliers in terms of assembly length '
                                                 '[default = False]', default=False, action='store_true')
    qcGroup.add_argument('--estimated-length', default=2000000, type = int, help='Provide an integer estimated genome length when using "--ignore-length" [default = 2000000]')


    # model fitting
    modelGroup = parser.add_argument_group('Model fit options')
    modelGroup.add_argument('--K', help='Maximum number of mixture components [default = 2]', type=int, default=2)
    modelGroup.add_argument('--dbscan', help='Use DBSCAN rather than mixture model', default=False, action='store_true')
    modelGroup.add_argument('--D', help='Maximum number of clusters in DBSCAN fitting [default = 100]', type=int, default=100)
    modelGroup.add_argument('--min-cluster-prop', help='Minimum proportion of points in a cluster '
                                                        'in DBSCAN fitting [default = 0.0001]', type=float, default=0.0001)

    # model refinement
    refinementGroup = parser.add_argument_group('Refine model options')
    refinementGroup.add_argument('--pos-shift', help='Maximum amount to move the boundary away from origin [default = 0.2]',
            type=float, default=0.2)
    refinementGroup.add_argument('--neg-shift', help='Maximum amount to move the boundary towards the origin [default = 0.4]',
            type=float, default=0.4)
    refinementGroup.add_argument('--manual-start', help='A file containing information for a start point. '
            'See documentation for help.', default=None)
    refinementGroup.add_argument('--indiv-refine', help='Also run refinement for core and accessory individually', default=False,
            action='store_true')
    refinementGroup.add_argument('--no-local', help='Do not perform the local optimization step (speed up on very large datasets)',
            default=False, action='store_true')

    # sequence querying
    queryingGroup = parser.add_argument_group('Database querying options')
    queryingGroup.add_argument('--model-dir', help='Directory containing model to use for assigning queries '
                                                   'to clusters [default = reference database directory]', type = str)
    queryingGroup.add_argument('--previous-clustering', help='Directory containing previous cluster definitions '
                                                             'and network [default = use that in the directory '
                                                             'containing the model]', type = str)
    queryingGroup.add_argument('--core-only', help='Use a core-distance only model for assigning queries '
                                              '[default = False]', default=False, action='store_true')
    queryingGroup.add_argument('--accessory-only', help='Use an accessory-distance only model for assigning queries '
                                              '[default = False]', default=False, action='store_true')

    # lineage clustering within strains
    lineagesGroup = parser.add_argument_group('Lineage analysis options')
    lineagesGroup.add_argument('--ranks',help='Comma separated list of ranks used in lineage clustering [default = 1,2,3]', type = str, default = "1,2,3")
    lineagesGroup.add_argument('--use-accessory',help='Use accessory distances for lineage definitions [default = use core distances]', action = 'store_true', default = False)
    lineagesGroup.add_argument('--existing-scheme',help='Name of pickle file storing existing lineage definitions '
                                                        ', required with "--assign-lineages"', type = str, default = None)

    # plot output
    faGroup = parser.add_argument_group('Further analysis options')
    faGroup.add_argument('--subset', help='File with list of sequences to include in visualisation (with --generate-viz only)', default=None)
    faGroup.add_argument('--microreact', help='Generate output files for microreact visualisation', default=False, action='store_true')
    faGroup.add_argument('--cytoscape', help='Generate network output files for Cytoscape', default=False, action='store_true')
    faGroup.add_argument('--phandango', help='Generate phylogeny and TSV for Phandango visualisation', default=False, action='store_true')
    faGroup.add_argument('--grapetree', help='Generate phylogeny and CSV for grapetree visualisation', default=False, action='store_true')
    faGroup.add_argument('--rapidnj', help='Path to rapidNJ binary to build NJ tree for Microreact', default=None)
    faGroup.add_argument('--perplexity', type=float, default = 20.0,
                         help='Perplexity used to calculate t-SNE projection (with --microreact) [default=20.0]')
    faGroup.add_argument('--info-csv',
                     help='Epidemiological information CSV formatted for microreact (can be used with other outputs)')

    # processing
    other = parser.add_argument_group('Other options')
    other.add_argument('--use-mash', default=False, action='store_true', help='Use the old mash sketch backend [default = False]')
    other.add_argument('--mash', default='mash', help='Location of mash executable')
    other.add_argument('--threads', default=1, type=int, help='Number of threads to use [default = 1]')
    other.add_argument('--use-gpu', default=False, action='store_true', help='Use a GPU when calculating distances [default = False]')
    other.add_argument('--deviceid', default=0, type=int, help='CUDA device ID, if using GPU [default = 0]')
    other.add_argument('--no-stream', help='Use temporary files for mash dist interfacing. Reduce memory use/increase disk use for large datasets', default=False, action='store_true')

    other.add_argument('--version', action='version',
                       version='%(prog)s '+__version__)


    # combine
    args = parser.parse_args()

    # ensure directories do not have trailing forward slash
    for arg in [args.ref_db,args.model_dir,args.previous_clustering]:
        if arg is not None:
            arg = arg.rstrip('\\')

    return args

def main():
    """Main function. Parses cmd line args and runs in the specified mode.
    """

    #******************************#
    #*                            *#
    #* Check command options      *#
    #*                            *#
    #******************************#
    if sys.version_info[0] < 3:
        sys.stderr.write('PopPUNK requires python version 3 or above\n')
        sys.exit(1)

    args = get_options()

    # establish method of kmer calculation
    if no_sketchlib:
        args.use_mash = True

    # check kmer properties
    if args.min_k >= args.max_k:
        sys.stderr.write("Minimum kmer size " + str(args.min_k) + " must be smaller than maximum kmer size\n")
        sys.exit(1)
    elif args.k_step < 2:
        sys.stderr.write("Kmer size step must be at least one\n")
        sys.exit(1)
    elif no_sketchlib and (args.min_k < 9 or args.max_k > 31):
        sys.stderr.write("When using Mash, Kmer size must be between 9 and 31\n")
        sys.exit(1)
    elif args.min_k < 5 or args.max_k > 51:
        sys.stderr.write("Very short or very long kmers are not recommended\n")
        sys.exit(1)
    kmers = np.arange(args.min_k, args.max_k + 1, args.k_step)

    # Dict of DB access functions for assign_query (which is out of scope)
    dbFuncs = setupDBFuncs(args, kmers, args.min_kmer_count)
    createDatabaseDir = dbFuncs['createDatabaseDir']
    constructDatabase = dbFuncs['constructDatabase']
    queryDatabase = dbFuncs['queryDatabase']
    readDBParams = dbFuncs['readDBParams']

    # define sketch sizes, store in hash in case one day
    # different kmers get different hash sizes
    sketch_sizes = {}
    if args.sketch_size >= 100 and args.sketch_size <= 10**6:
        for k in kmers:
            sketch_sizes[k] = args.sketch_size
    else:
        sys.stderr.write("Sketch size should be between 100 and 10^6\n")
        sys.exit(1)
    # for sketchlib, only supporting a single sketch size
    if not args.use_mash:
        sketch_sizes = int(round(max(sketch_sizes.values())/64))

    # check if working with lineages
    rank_list = []
    if args.lineage_clustering or args.assign_lineages:
        rank_list = sorted([int(x) for x in args.ranks.split(',')])
        if min(rank_list) == 0 or max(rank_list) > 100:
            sys.stderr.write('Ranks should be small non-zero integers for sensible results\n')
            exit(1)
        if args.assign_lineages and args.existing_scheme is None:
            sys.stderr.write('Must provide an existing scheme (--existing-scheme) if assigning to lineages\n')
            exit(1)

    # check on file paths and whether files will be overwritten
    # confusing to overwrite command line parameter
    #if not args.full_db and not (args.create_db or args.easy_run or args.assign_query):
    #    args.overwrite = True
    if args.output is not None and args.output.endswith('/'):
        args.output = args.output[:-1]
    if args.ref_db is not None and args.ref_db.endswith('/'):
        args.ref_db = args.ref_db[:-1]

    # run according to mode
    sys.stderr.write("PopPUNK (POPulation Partitioning Using Nucleotide Kmers)\n")
    sys.stderr.write("\t(with backend: " + dbFuncs['backend'] + " v" + dbFuncs['backend_version'] + "\n")
    if (dbFuncs['backend'] == 'sketchlib'):
        sketchlib_version = [int(x) for x in dbFuncs['backend_version'].split(".")]
        if sketchlib_version[0] < SKETCHLIB_MAJOR or sketchlib_version[1] < SKETCHLIB_MINOR:
            sys.stderr.write("This version of PopPUNK requires sketchlib v1.3.0 or higher\n")
            sys.exit(1)
        else:
            sys.stderr.write('\t sketchlib: ' + checkSketchlibLibrary() + ')\n')

    #******************************#
    #*                            *#
    #* Create database            *#
    #*                            *#
    #******************************#
    if args.create_db or args.easy_run:
        if args.create_db:
            sys.stderr.write("Mode: Building new database from input sequences\n")
        elif args.easy_run:
            sys.stderr.write("Mode: Creating clusters from assemblies (create_db & fit_model)\n")
        if args.r_files is not None:
            # Sketch
            createDatabaseDir(args.output, kmers)
            constructDatabase(args.r_files, kmers, sketch_sizes, args.output, args.estimated_length, args.ignore_length, args.threads,
                args.overwrite)

            # Calculate and QC distances
            if args.use_mash == True:
                rNames = None
                qNames = readRfile(args.r_files, oneSeq=True)[1]
            else:
                rNames = readRfile(args.r_files)[0]
                qNames = rNames
            refList, queryList, distMat = queryDatabase(rNames = rNames,
                                                        qNames = qNames,
                                                        dbPrefix = args.output,
                                                        queryPrefix = args.output,
                                                        klist = kmers,
                                                        self = True,
                                                        number_plot_fits = args.plot_fit,
                                                        threads = args.threads)
            qcDistMat(distMat, refList, queryList, args.max_a_dist)

            # Save results
            dists_out = args.output + "/" + os.path.basename(args.output) + ".dists"
            storePickle(refList, queryList, True, distMat, dists_out)
        else:
            sys.stderr.write("Need to provide a list of reference files with --r-files")
            sys.exit(1)

    #******************************#
    #*                            *#
    #* model fit and network      *#
    #* construction               *#
    #*                            *#
    #******************************#
    # refine model also needs to run all model steps
    if args.fit_model or args.use_model or args.refine_model or args.threshold or args.easy_run:
        # Set up saved data from first step, if easy_run mode
        if args.easy_run:
            distances = dists_out
            ref_db = args.output
        else:
            if args.fit_model:
                sys.stderr.write("Mode: Fitting model to reference database\n\n")
            elif args.use_model:
                sys.stderr.write("Mode: Using previous model with a reference database\n\n")
            elif args.threshold:
                sys.stderr.write("Mode: Applying a core distance threshold\n\n")
            else:
                sys.stderr.write("Mode: Refining model fit using network properties\n\n")

            if args.distances is not None and args.ref_db is not None:
                distances = args.distances
                ref_db = args.ref_db
            else:
                sys.stderr.write("Need to provide an input set of distances with --distances "
                                 "and reference database directory with --ref-db\n\n")
                sys.exit(1)

        # Set up variables for using previous models
        if args.refine_model or args.use_model:
            model_prefix = args.ref_db
            if args.model_dir is not None:
                model_prefix = args.model_dir
            model = loadClusterFit(model_prefix + "/" + os.path.basename(model_prefix) + '_fit.pkl',
                        model_prefix + "/" + os.path.basename(model_prefix) + '_fit.npz',
                        args.output)
            if args.refine_model and model.type == 'refine':
                sys.stderr.write("Model needs to be from --fit-model not --refine-model\n")
                sys.exit(1)

        # Load the distances
        refList, queryList, self, distMat = readPickle(distances)
        if not self:
            sys.stderr.write("Model fit should be to a reference db made with --create-db\n")
            sys.exit(1)
        if qcDistMat(distMat, refList, queryList, args.max_a_dist) == False:
            sys.stderr.write("Distances failed quality control (change QC options to run anyway)\n")
            sys.exit(1)

        #******************************#
        #*                            *#
        #* model fit                  *#
        #*                            *#
        #******************************#
        # Run selected model here, or if easy run DBSCAN followed by refinement
        if args.fit_model or args.easy_run:
            # Run DBSCAN model
            if args.dbscan or args.easy_run:
                model = DBSCANFit(args.output)
                assignments = model.fit(distMat, args.D, args.min_cluster_prop)
                model.plot()
            # Run Gaussian model
            else:
                model = BGMMFit(args.output)
                assignments = model.fit(distMat, args.K)
                model.plot(distMat, assignments)

        # Run model refinement
        if args.refine_model or args.threshold or args.easy_run:
            new_model = RefineFit(args.output)
            if args.threshold == None:
                assignments = new_model.fit(distMat, refList, model, args.pos_shift, args.neg_shift,
                        args.manual_start, args.indiv_refine, args.no_local, args.threads)
            else:
                assignments = new_model.apply_threshold(distMat, args.threshold)

            new_model.plot(distMat)
            model = new_model

        # Load and apply a previous model of any type
        if args.use_model:
            assignments = model.assign(distMat)
            model.plot(distMat, assignments)

        fit_type = 'combined'
        model.save()

        #******************************#
        #*                            *#
        #* network construction       *#
        #*                            *#
        #******************************#
        genomeNetwork = constructNetwork(refList, queryList, assignments, model.within_label)

        # Ensure all in dists are in final network
        networkMissing = set(refList).difference(list(genomeNetwork.nodes()))
        if len(networkMissing) > 0:
            sys.stderr.write("WARNING: Samples " + ",".join(networkMissing) + " are missing from the final network\n")

        isolateClustering = {fit_type: printClusters(genomeNetwork,
                                                     args.output + "/" + os.path.basename(args.output),
                                                     externalClusterCSV = args.external_clustering)}

        # Write core and accessory based clusters, if they worked
        if model.indiv_fitted:
            indivNetworks = {}
            for dist_type, slope in zip(['core', 'accessory'], [0, 1]):
                indivAssignments = model.assign(distMat, slope)
                indivNetworks[dist_type] = constructNetwork(refList, queryList, indivAssignments, model.within_label)
                isolateClustering[dist_type] = printClusters(indivNetworks[dist_type],
                                                 args.output + "/" + os.path.basename(args.output) + "_" + dist_type,
                                                 externalClusterCSV = args.external_clustering)
                nx.write_gpickle(indivNetworks[dist_type], args.output + "/" + os.path.basename(args.output) +
                                                           "_" + dist_type + '_graph.gpickle')
            if args.core_only:
                fit_type = 'core'
                genomeNetwork = indivNetworks['core']
            elif args.accessory_only:
                fit_type = 'accessory'
                genomeNetwork = indivNetworks['accessory']

        #******************************#
        #*                            *#
        #* external visualisations    *#
        #*                            *#
        #******************************#
        # Create files for visualisations
        try:
            if args.microreact or args.cytoscape or args.phandango or args.grapetree:
                # generate distance matrices for outputs if required
                combined_seq, core_distMat, acc_distMat = \
                    update_distance_matrices(refList, distMat, threads = args.threads)

                if args.microreact:
                    sys.stderr.write("Writing microreact output\n")
                    outputsForMicroreact(refList, core_distMat, acc_distMat, isolateClustering, args.perplexity,
                                        args.output, args.info_csv, args.rapidnj, overwrite = args.overwrite)
                if args.phandango:
                    sys.stderr.write("Writing phandango output\n")
                    outputsForPhandango(refList, core_distMat, isolateClustering, args.output, args.info_csv, args.rapidnj,
                                        overwrite = args.overwrite, microreact = args.microreact)
                if args.grapetree:
                    sys.stderr.write("Writing grapetree output\n")
                    outputsForGrapetree(refList, core_distMat, isolateClustering, args.output, args.info_csv, args.rapidnj,
                                        overwrite = args.overwrite, microreact = args.microreact)
                if args.cytoscape:
                    sys.stderr.write("Writing cytoscape output\n")
                    outputsForCytoscape(genomeNetwork, isolateClustering, args.output, args.info_csv)
                    if model.indiv_fitted:
                        sys.stderr.write("Writing individual cytoscape networks\n")
                        for dist_type in ['core', 'accessory']:
                            outputsForCytoscape(indivNetworks[dist_type], isolateClustering, args.output,
                                        args.info_csv, suffix = dist_type, writeCsv = False)
        except:
            # Go ahead with final steps even if visualisations fail
            # (e.g. rapidnj not found)
            sys.stderr.write("Error creating files for visualisation:" + str(sys.exc_info()[0]))

        #******************************#
        #*                            *#
        #* clique pruning             *#
        #*                            *#
        #******************************#
        # extract limited references from clique by default
        if not args.full_db:
            newReferencesNames, newReferencesFile = extractReferences(genomeNetwork, refList, args.output)
            nodes_to_remove = set(refList).difference(newReferencesNames)
            genomeNetwork.remove_nodes_from(nodes_to_remove)
            prune_distance_matrix(refList, nodes_to_remove, distMat,
                                  args.output + "/" + os.path.basename(args.output) + ".dists")

            # With mash, the sketches are actually removed from the database
            if args.use_mash:
                # Create compatible input file
                dummyRefFile = writeDummyReferences(newReferencesNames, args.output)
                # Read and overwrite previous database
                kmers, sketch_sizes = readDBParams(ref_db, kmers, sketch_sizes)
                constructDatabase(dummyRefFile, kmers, sketch_sizes, args.output,
                                args.estimated_length, True, args.threads, True) # overwrite old db
                os.remove(dummyRefFile)

        nx.write_gpickle(genomeNetwork, args.output + "/" + os.path.basename(args.output) + '_graph.gpickle')

    #******************************#
    #*                            *#
    #* within-strain analysis     *#
    #*                            *#
    #******************************#
    if args.lineage_clustering:
        sys.stderr.write("Mode: Identifying lineages within a clade\n\n")

        # load distances
        if args.distances is not None:
            distances = args.distances
        else:
            sys.stderr.write("Need to provide an input set of distances with --distances\n\n")
            sys.exit(1)

        refList, queryList, self, distMat = readPickle(distances)

        # make directory for new output files
        if not os.path.isdir(args.output):
            try:
                os.makedirs(args.output)
            except OSError:
                sys.stderr.write("Cannot create output directory\n")
                sys.exit(1)

        # run lineage clustering
        if self:
            isolateClustering = cluster_into_lineages(distMat, rank_list, args.output, isolate_list = refList, use_accessory = args.use_accessory, existing_scheme = args.existing_scheme, num_processes = args.threads)
        else:
            isolateClustering = cluster_into_lineages(distMat, rank_list, args.output, isolate_list = refList, qlist = queryList, use_accessory = args.use_accessory,  existing_scheme = args.existing_scheme, num_processes = args.threads)

    #*******************************#
    #*                             *#
    #* query assignment (function  *#
    #* below)                      *#
    #*                             *#
    #*******************************#
    elif args.assign_query or args.assign_lineages:
        assign_query(dbFuncs, args.ref_db, args.q_files, args.output, args.update_db, args.full_db, args.distances,
                     args.microreact, args.cytoscape, kmers, sketch_sizes, args.ignore_length, args.estimated_length,
                     args.threads, args.use_mash, args.mash, args.overwrite, args.plot_fit, args.no_stream,
                     args.max_a_dist, args.model_dir, args.previous_clustering, args.external_clustering,
                     args.core_only, args.accessory_only, args.phandango, args.grapetree, args.info_csv,
                     args.rapidnj, args.perplexity, args.assign_lineages, args.existing_scheme, rank_list, args.use_accessory)

    #******************************#
    #*                            *#
    #* generate viz mode          *#
    #*                            *#
    #******************************#
    # generate visualisation files from existing database
    elif args.generate_viz:
        if args.microreact or args.phandango or args.grapetree or args.cytoscape:
            sys.stderr.write("Mode: Generating files for visualisation from database\n\n")
        else:
            sys.stderr.write("Must specify at least one type of visualisation to output\n")
            sys.exit(1)

        if args.distances is not None and args.ref_db is not None:

            # Initial processing
            # Load original distances
            with open(args.distances + ".pkl", 'rb') as pickle_file:
                rlist, qlist, self = pickle.load(pickle_file)
                complete_distMat = np.load(args.distances + ".npy")
                combined_seq, core_distMat, acc_distMat = \
                    update_distance_matrices(rlist, complete_distMat,
                                             threads = args.threads)

            # make directory for new output files
            if not os.path.isdir(args.output):
                try:
                    os.makedirs(args.output)
                except OSError:
                    sys.stderr.write("Cannot create output directory\n")
                    sys.exit(1)

            # Define set/subset to be visualised
            # extract subset of distances if requested
            viz_subset = rlist
            if args.subset is not None:
                viz_subset = []
                with open(args.subset, 'r') as assemblyFiles:
                    for assembly in assemblyFiles:
                        viz_subset.append(assembly.rstrip())

            # Use the same code as no full_db in assign_query to take a subset
            dists_out = args.output + "/" + os.path.basename(args.output) + ".dists"
            #nodes_to_remove = set(genomeNetwork.nodes).difference(viz_subset)
            isolates_to_remove = set(combined_seq).difference(viz_subset)
            postpruning_combined_seq = viz_subset
            newDistMat = complete_distMat
            if len(isolates_to_remove) > 0:
                postpruning_combined_seq, newDistMat = prune_distance_matrix(rlist, isolates_to_remove,
                                                                      complete_distMat, dists_out)

            rlist = viz_subset
            combined_seq, core_distMat, acc_distMat = \
                update_distance_matrices(viz_subset, newDistMat,
                                         threads = args.threads)

            # reorder subset to ensure list orders match
            try:
                viz_subset = sorted(viz_subset,key=postpruning_combined_seq.index)
            except:
                sys.stderr.write("Isolates in subset not found in existing database\n")
            assert postpruning_combined_seq == viz_subset

            # Either use strain definitions, lineage assignments or external clustering
            isolateClustering = {}
            # Use external clustering if specified
            if args.external_clustering:
                cluster_file = args.external_clustering
                isolateClustering = readIsolateTypeFromCsv(cluster_file, mode = 'external', return_dict = True)
            if args.viz_lineages:
                cluster_file = args.viz_lineages
                isolateClustering = readIsolateTypeFromCsv(cluster_file, mode = 'lineages', return_dict = True)
            else:
                # identify existing analysis files
                model_prefix = args.ref_db
                if args.model_dir is not None:
                    model_prefix = args.model_dir
                model = loadClusterFit(model_prefix + "/" + os.path.basename(model_prefix) + '_fit.pkl',
                                   model_prefix + "/" + os.path.basename(model_prefix) + '_fit.npz')

                # Set directories of previous fit
                if args.previous_clustering is not None:
                    prev_clustering = args.previous_clustering
                else:
                    prev_clustering = os.path.dirname(args.distances + ".pkl")

                # Read in network and cluster assignment
                genomeNetwork, cluster_file = fetchNetwork(prev_clustering, model, rlist, args.core_only, args.accessory_only)
                isolateClustering = readIsolateTypeFromCsv(cluster_file, mode = 'clusters', return_dict = True)

                # prune the network and dictionary of assignments
                genomeNetwork.remove_nodes_from(set(genomeNetwork.nodes).difference(viz_subset))

            # generate selected visualisations
            if args.microreact:
                sys.stderr.write("Writing microreact output\n")
                outputsForMicroreact(viz_subset, core_distMat, acc_distMat, isolateClustering, args.perplexity,
                                     args.output, args.info_csv, args.rapidnj, overwrite = args.overwrite)
            if args.phandango:
                sys.stderr.write("Writing phandango output\n")
                outputsForPhandango(viz_subset, core_distMat, isolateClustering, args.output, args.info_csv, args.rapidnj,
                                    overwrite = args.overwrite, microreact = args.microreact)
            if args.grapetree:
                sys.stderr.write("Writing grapetree output\n")
                outputsForGrapetree(viz_subset, core_distMat, isolateClustering, args.output, args.info_csv, args.rapidnj,
                                    overwrite = args.overwrite, microreact = args.microreact)
            if args.cytoscape:
                if args.viz_lineages or args.external_clustering:
                    sys.stderr.write("Can only generate a network output for fitted models\n")
                else:
                    sys.stderr.write("Writing cytoscape output\n")
                    outputsForCytoscape(genomeNetwork, isolateClustering, args.output, args.info_csv)

        else:
            # Cannot read input files
            sys.stderr.write("Need to provide an input set of distances with --distances "
                             "and reference database directory with --ref-db\n\n")
            sys.exit(1)

    sys.stderr.write("\nDone\n")

#*******************************#
#*                             *#
#* query assignment            *#
#*                             *#
#*******************************#
def assign_query(dbFuncs, ref_db, q_files, output, update_db, full_db, distances, microreact, cytoscape,
                 kmers, sketch_sizes, ignore_length, estimated_length, threads, use_mash, mash, overwrite,
                 plot_fit, no_stream, max_a_dist, model_dir, previous_clustering,
                 external_clustering, core_only, accessory_only, phandango, grapetree,
                 info_csv, rapidnj, perplexity, assign_lineage, existing_scheme, rank_list, use_accessory):
    """Code for assign query mode. Written as a separate function so it can be called
    by pathogen.watch API
    """
    createDatabaseDir = dbFuncs['createDatabaseDir']
    joinDBs = dbFuncs['joinDBs']
    constructDatabase = dbFuncs['constructDatabase']
    queryDatabase = dbFuncs['queryDatabase']
    readDBParams = dbFuncs['readDBParams']
    getSeqsInDb = dbFuncs['getSeqsInDb']

    if ref_db is not None and q_files is not None:
        sys.stderr.write("Mode: Assigning clusters of query sequences\n\n")
        self = False
        if ref_db == output:
            sys.stderr.write("--output and --ref-db must be different to "
                                "prevent overwrite.\n")
            sys.exit(1)
        if (update_db and not distances):
            sys.stderr.write("--update-db requires --distances to be provided\n")
            sys.exit(1)
        if (microreact or cytoscape) and (not update_db or not distances):
            sys.stderr.write("--microreact and/or --cytoscape output must be "
                    "run with --distances and --update-db to generate a full "
                    " distance matrix\n")
            sys.exit(1)

        # Find distances to reference db
        kmers, sketch_sizes = readDBParams(ref_db, kmers, sketch_sizes)

        # Sketch query sequences
        createDatabaseDir(output, kmers)
        constructDatabase(q_files, kmers, sketch_sizes, output,
                            estimated_length, ignore_length, threads, overwrite)

        # Find distances vs ref seqs
        rNames = []
        if use_mash == True:
            rNames = None
            qNames = readRfile(q_files, oneSeq=True)[1]
        else:
            qNames = readRfile(q_files)[0]
            if os.path.isfile(ref_db + "/" + os.path.basename(ref_db) + ".refs"):
                with open(ref_db + "/" + os.path.basename(ref_db) + ".refs") as refFile:
                    for reference in refFile:
                        rNames.append(reference.rstrip())
            else:
                rNames = getSeqsInDb(ref_db + "/" + os.path.basename(ref_db) + ".h5")

        refList, queryList, distMat = queryDatabase(rNames = rNames,
                                                    qNames = qNames,
                                                    dbPrefix = ref_db,
                                                    queryPrefix = output,
                                                    klist = kmers,
                                                    self = False,
                                                    number_plot_fits = plot_fit,
                                                    threads = threads)
        qcPass = qcDistMat(distMat, refList, queryList, max_a_dist)

        # Calculate query-query distances
        ordered_queryList = []

        # Assign to strains or lineages, as requested
        if assign_lineage:

            # Assign lineages by calculating query-query information
            ordered_queryList, query_distMat = calculateQueryQueryDistances(dbFuncs, refList, q_files,
                    kmers, estimated_length, output, use_mash, threads)

        else:
            # Assign these distances as within or between strain
            model_prefix = ref_db
            if model_dir is not None:
                model_prefix = model_dir
            model = loadClusterFit(model_prefix + "/" + os.path.basename(model_prefix) + '_fit.pkl',
                                    model_prefix + "/" + os.path.basename(model_prefix) + '_fit.npz')
            queryAssignments = model.assign(distMat)

            # set model prefix
            model_prefix = ref_db
            if model_dir is not None:
                model_prefix = model_dir

            # Set directories of previous fit
            if previous_clustering is not None:
                prev_clustering = previous_clustering
            else:
                prev_clustering = model_prefix

            # Load the network based on supplied options
            genomeNetwork, old_cluster_file = fetchNetwork(prev_clustering, model, refList,
                                                            core_only, accessory_only)

            # Assign clustering by adding to network
            ordered_queryList, query_distMat = addQueryToNetwork(dbFuncs, refList, q_files,
                    genomeNetwork, kmers, estimated_length, queryAssignments, model, output, update_db,
                    use_mash, threads)

            # if running simple query
            print_full_clustering = False
            if update_db:
                print_full_clustering = True
            isolateClustering = {'combined': printClusters(genomeNetwork, output + "/" + os.path.basename(output),
                                                            old_cluster_file, external_clustering, print_full_clustering)}

        # Update DB as requested
        if update_db or assign_lineage:

            # Check new sequences pass QC before adding them
            if not qcPass:
                sys.stderr.write("Queries contained outlier distances, not updating database\n")
            else:
                sys.stderr.write("Updating reference database to " + output + "\n")

            # Update the network + ref list
            # only update network if assigning to strains
            if full_db is False and assign_lineage is False:
                mashOrder = refList + ordered_queryList
                newRepresentativesNames, newRepresentativesFile = extractReferences(genomeNetwork, mashOrder, output, refList)
                genomeNetwork.remove_nodes_from(set(genomeNetwork.nodes).difference(newRepresentativesNames))
                newQueries = [x for x in ordered_queryList if x in frozenset(newRepresentativesNames)] # intersection that maintains order
                nx.write_gpickle(genomeNetwork, output + "/" + os.path.basename(output) + '_graph.gpickle')
            else:
                newQueries = ordered_queryList

            # Update the sketch database
            if newQueries != queryList and use_mash:
                tmpRefFile = writeTmpFile(newQueries)
                constructDatabase(tmpRefFile, kmers, sketch_sizes, output,
                                    args.estimated_length, True, threads, True) # overwrite old db
                os.remove(tmpRefFile)
            # With mash, this is the reduced DB constructed,
            # with sketchlib, all sketches
            joinDBs(ref_db, output, output)

            # Update distance matrices with all calculated distances
            if distances == None:
                distanceFiles = ref_db + "/" + os.path.basename(ref_db) + ".dists"
            else:
                distanceFiles = distances
            refList, refList_copy, self, ref_distMat = readPickle(distanceFiles)
            combined_seq, core_distMat, acc_distMat = \
                update_distance_matrices(refList, ref_distMat,
                                         ordered_queryList, distMat,
                                         query_distMat, threads = threads)
            complete_distMat = \
                np.hstack((pp_sketchlib.squareToLong(core_distMat, threads).reshape(-1, 1),
                           pp_sketchlib.squareToLong(acc_distMat, threads).reshape(-1, 1)))

            if assign_lineage:
                expected_lineage_name = ref_db + '/' + ref_db + '_lineages.pkl'
                if existing_scheme is not None:
                    expected_lineage_name = existing_scheme
                isolateClustering = cluster_into_lineages(complete_distMat,
                                                          rank_list, output,
                                                          combined_seq,
                                                          ordered_queryList,
                                                          expected_lineage_name,
                                                          use_accessory,
                                                          threads)

            # Prune distances to references only, if not full db
            dists_out = output + "/" + os.path.basename(output) + ".dists"
            if full_db is False and assign_lineage is False:
                # could also have newRepresentativesNames in this diff (should be the same) - but want
                # to ensure consistency with the network in case of bad input/bugs
                nodes_to_remove = set(combined_seq).difference(genomeNetwork.nodes)
                # This function also writes out the new distance matrix
                postpruning_combined_seq, newDistMat = prune_distance_matrix(combined_seq, nodes_to_remove,
                                                                                complete_distMat, dists_out)

                # ensure mash sketch and distMat order match
                assert postpruning_combined_seq == refList + newQueries

            else:
                storePickle(combined_seq, combined_seq, True, complete_distMat, dists_out)

                # ensure mash sketch and distMat order match
                assert combined_seq == refList + newQueries

        # Generate files for visualisations
        if microreact:
            sys.stderr.write("Writing microreact output\n")
            outputsForMicroreact(combined_seq, core_distMat, acc_distMat, isolateClustering, perplexity,
                                    output, info_csv, rapidnj, ordered_queryList, overwrite)
        if phandango:
            sys.stderr.write("Writing phandango output\n")
            outputsForPhandango(combined_seq, core_distMat, isolateClustering, output, info_csv, rapidnj,
                                queryList = ordered_queryList, overwrite = overwrite, microreact = microreact)
        if grapetree:
            sys.stderr.write("Writing grapetree output\n")
            outputsForGrapetree(combined_seq, core_distMat, isolateClustering, output, info_csv, rapidnj,
                                queryList = ordered_queryList, overwrite = overwrite, microreact = microreact)
        if cytoscape:
            if assign_lineage:
                sys.stderr.write("Cannot generate a cytoscape network from a lineage assignment")
            else:
                sys.stderr.write("Writing cytoscape output\n")
                outputsForCytoscape(genomeNetwork, isolateClustering, output, info_csv, ordered_queryList)

    else:
        sys.stderr.write("Need to provide both a reference database with --ref-db and "
                            "query list with --q-files\n")
        sys.exit(1)

    return(isolateClustering)


if __name__ == '__main__':
    main()

    sys.exit(0)
