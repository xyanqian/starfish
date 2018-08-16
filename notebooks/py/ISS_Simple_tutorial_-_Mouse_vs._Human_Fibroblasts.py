#!/usr/bin/env python
# coding: utf-8
#
# EPY: stripped_notebook: {"metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"codemirror_mode": {"name": "ipython", "version": 3}, "file_extension": ".py", "mimetype": "text/x-python", "name": "python", "nbconvert_exporter": "python", "pygments_lexer": "ipython3", "version": "3.6.5"}}, "nbformat": 4, "nbformat_minor": 2}

# EPY: START markdown
# # User note: This notebook is currently broken
# 
# For a working ISS demonstration, please see the ISS_Pipeline notebook in the same directory
# EPY: END markdown

# EPY: START markdown
# # Starfish re-creation of an in-situ sequencing pipeline 
# 
# Here, we reproduce the results of a pipeline run on data collected using the gap filling and padlock probe litigation method described in [Ke, Mignardi, et. al, 2013](http://www.nature.com/nmeth/journal/v10/n9/full/nmeth.2563.html). These data represent 5 co-cultured mouse and human cells -- the main idea is to detect a single nucleotide polymorphism (SNP) in the Beta-Actin (ACTB) gene across species. The Python code below correctly re-produces the same results from the original cell profiler - matlab - imagej [pipeline](http://cellprofiler.org/examples/#InSitu) that is publicly accessible. 
# EPY: END markdown

# EPY: START code
# EPY: ESCAPE %matplotlib notebook

import pandas as pd
import numpy as np
from skimage.color import rgb2gray

import matplotlib.pyplot as plt
from showit import image, tile

from starfish.constants import Indices, Features
# EPY: END code

# EPY: START markdown
# ## Raw Data
# 
# The raw data can be downloaded and formatted for analysis by running: ```python examples/get_iss_data.py ><raw data directory> <output directory> --d 1``` from the Starfish directory
# EPY: END markdown

# EPY: START code
from starfish.experiment import Experiment

# replace <output directory> with where you saved the formatted data to with the above script
in_json = '<output directory>/org.json'
experiment = Experiment.from_json(in_json)

tile(experiment.image.squeeze(), size=10);
# EPY: END code

# EPY: START code
image(experiment.auxiliary_images['dots'], size=10)
# EPY: END code

# EPY: START markdown
# ## Register
# EPY: END markdown

# EPY: START code
from starfish.image import Registration

registration = Registration.fourier_shift(upsampling=1000)
registration.run(experiment)

tile(experiment.image.squeeze(), size=10);
# EPY: END code

# EPY: START markdown
# ## Filter
# EPY: END markdown

# EPY: START code
from starfish.image import Filter

disk_dize = 10

# filter raw images, for all rounds and channels
stack_filt = [white_top_hat(im, disk_dize) for im in experiment.image.squeeze()]
stack_filt = experiment.un_squeeze(stack_filt)

# filter dots
dots_filt = white_top_hat(experiment.auxiliary_images['dots'], disk_dize)

# create a 'stain' for segmentation
stain = np.mean(experiment.image.max_proj(Indices.CH), axis=0)
stain = stain/stain.max()

# update stack
experiment.set_stack(stack_filt)
experiment.set_aux('dots', dots_filt)
experiment.set_aux('stain', stain)

# visualize
tile(experiment.image.squeeze(), bar=False, size=10);
image(experiment.auxiliary_images['dots'])
image(experiment.auxiliary_images['stain'])
# EPY: END code

# EPY: START markdown
# ## Detect
# EPY: END markdown

# EPY: START code
from starfish.spots import SpotFinder

gsp = SpotFinder.GaussianSpotDetector(experiment)
min_sigma = 4
max_sigma = 6
num_sigma=20
thresh=.01
blobs='dots'
measurement_type="max"
bit_map_flag=False

spots_df_tidy = gsp.detect(min_sigma, max_sigma, num_sigma, thresh, blobs, measurement_type, bit_map_flag)
gsp.show(figsize=(10,10))
    
spots_viz = gsp.spots_df_viz
spots_df_tidy.head()
# EPY: END code

# EPY: START code
spots_viz.head()
# EPY: END code

# EPY: START markdown
# ##  Segmentation
# EPY: END markdown

# EPY: START code
from starfish.image import Segmentation

dapi_thresh = .16
stain_thresh = .22
size_lim = (10, 10000)
disk_size_markers = None
disk_size_mask = None
min_dist = 57

seg = Segmentation.WatershedSegmenter(experiment.auxiliary_images['dapi'], experiment.auxiliary_images['stain'])
cells_labels = seg.run(dapi_thresh, stain_thresh, size_lim, disk_size_markers, disk_size_mask, min_dist)
seg.show()
# EPY: END code

# EPY: START markdown
# ## Assignment
# EPY: END markdown

# EPY: START code
from starfish.spots import TargetAssignment
from starfish.stats import label_to_regions

points = spots_viz.loc[:, [Features.X, Features.Y]].values
regions = label_to_regions(cells_labels)
ass = assign(regions, points, use_hull=True)
ass.groupby('cell_id',as_index=False).count().rename(columns={'spot_id':'num spots'})
# EPY: END code

# EPY: START code
ass.head()
# EPY: END code

# EPY: START markdown
# ## Decode
# EPY: END markdown

# EPY: START code
from starfish.decoders.iss import IssDecoder

decoder = IssDecoder(pd.DataFrame({'barcode': ['AAGC', 'AGGC'], 'gene': ['ACTB_human', 'ACTB_mouse']}), 
                     letters=['T', 'G', 'C', 'A'])
dec = decoder.metric_decode(spots_df_tidy)
dec.qual.hist(bins=20)
top_barcode = dec.barcode.value_counts()[0:10]
top_barcode
# EPY: END code

# EPY: START markdown
# ## Visualization
# EPY: END markdown

# EPY: START code
from starfish.stats import label_to_regions

dec_filt = pd.merge(dec, spots_viz, on='spot_id',how='left')
dec_filt = dec_filt[dec_filt.qual>.25]

assert experiment.auxiliary_images['dapi'].shape == experiment.auxiliary_images['dots'].shape

rgb = np.zeros(experiment.auxiliary_images['dapi'].shape + (3,))
rgb[:,:,0] = experiment.auxiliary_images['dapi']
rgb[:,:,1] = experiment.auxiliary_images['dots']
do = rgb2gray(rgb)
do = do/(do.max())

image(do,size=10)
plt.plot(dec_filt[dec_filt.barcode==top_barcode.index[0]].y, 
         dec_filt[dec_filt.barcode==top_barcode.index[0]].x, 
         'ob', 
         markerfacecolor='None')

plt.plot(dec_filt[dec_filt.barcode==top_barcode.index[1]].y, dec_filt[dec_filt.barcode==top_barcode.index[1]].x, 'or', markerfacecolor='None')

v = pd.merge(spots_viz, ass, on='spot_id')

r = label_to_regions(cells_labels)
im = r.mask(background=[0.9, 0.9, 0.9], dims=experiment.auxiliary_images['dots'].shape, stroke=None, cmap='rainbow')
image(im,size=10)

v_ass = v[~v.cell_id.isnull()]
plt.plot(v_ass.y, v_ass.x, '.w')

v_uass = v[v.cell_id.isnull()]
plt.plot(v_uass.y, v_uass.x, 'xw')
# EPY: END code

# EPY: START markdown
# ## Cell by gene expression table
# EPY: END markdown

# EPY: START code
res = pd.merge(dec, ass, on='spot_id', how='left')
grp = res.groupby(['barcode', 'cell_id'],as_index=False).count()
exp_tab = grp.pivot(index='cell_id', columns='barcode', values = 'spot_id').fillna(0)
exp_tab
# EPY: END code
