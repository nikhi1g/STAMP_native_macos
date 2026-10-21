#=======================================================================
# Author: Donovan Parks
#
# Abstract base class specifying interface of a multiple group plot plugin.
#
# Copyright 2011 Donovan Parks
#
# This file is part of STAMP.
#
# STAMP is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# STAMP is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with STAMP.  If not, see <http://www.gnu.org/licenses/>.
#======================================================================='''

import time
import functools

from PyQt6 import QtGui, QtCore, QtWidgets

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.transforms as mtransforms

import numpy as np

# ponytail: matplotlib 2.0 changed these rc defaults and upstream (matplotlib 1.4) relied on
# them implicitly. They are applied only while a multiple group plot is drawn or saved (see
# mpl14Defaults), so plots look as in STAMP 2.1.3. Keys STAMP.py sets itself (font sizes,
# svg.fonttype) are deliberately absent. Upgrade path: if every plot family adopts the same
# table, hoist it into STAMP.py once and drop this wrapper.
MPL_1_4_RC = {
	'lines.linewidth': 1.0,
	'lines.markeredgewidth': 0.5,
	'lines.dashed_pattern': [6, 6],
	'lines.dashdot_pattern': [3, 5, 1, 5],
	'lines.dotted_pattern': [1, 3],
	'lines.scale_dashes': False,
	'patch.linewidth': 1.0,
	'patch.force_edgecolor': True,
	'patch.edgecolor': 'k',
	'scatter.edgecolors': 'k',
	'errorbar.capsize': 3,
	'axes.linewidth': 1.0,
	'axes.titlepad': 5.0,
	'axes.labelpad': 5.0,
	'axes.autolimit_mode': 'round_numbers',
	'axes.xmargin': 0,
	'axes.ymargin': 0,
	'axes.formatter.offset_threshold': 2,
	'xtick.direction': 'in',
	'ytick.direction': 'in',
	'xtick.top': True,
	'ytick.right': True,
	'xtick.major.size': 4,
	'ytick.major.size': 4,
	'xtick.minor.size': 2,
	'ytick.minor.size': 2,
	'xtick.major.width': 0.5,
	'ytick.major.width': 0.5,
	'xtick.minor.width': 0.5,
	'ytick.minor.width': 0.5,
	'xtick.major.pad': 4,
	'ytick.major.pad': 4,
	'xtick.minor.pad': 4,
	'ytick.minor.pad': 4,
	'legend.fancybox': False,
	'legend.numpoints': 2,
	'legend.scatterpoints': 3,
	'legend.framealpha': None,
	'legend.edgecolor': 'inherit',
	'mathtext.fontset': 'cm',
}

def mpl14Defaults(method):
	'''Run a plotting method with the matplotlib 1.4 defaults in MPL_1_4_RC.'''
	@functools.wraps(method)
	def wrapper(*args, **kwargs):
		with mpl.rc_context(MPL_1_4_RC):
			return method(*args, **kwargs)
	return wrapper

class AbstractMultiGroupPlotPlugin(FigureCanvas):
	'''
	Abstract base class specifying interface of a multiple group plot plugin.
	'''
	def __init__(self, preferences, parent=None):	
		self.preferences = preferences
		
		self.fig = Figure(facecolor='white', dpi=96)
		
		FigureCanvas.__init__(self, self.fig)
		
		self.setParent(parent)
		FigureCanvas.setSizePolicy(self,
														 QtWidgets.QSizePolicy.Policy.Fixed,
														 QtWidgets.QSizePolicy.Policy.Fixed)
		FigureCanvas.updateGeometry(self)
		
		self.cid = None
		
		self.type = '<none>'
		self.name = '<none>'
		self.bSupportsHighlight = False
		self.bPlotFeaturesIndividually = True
		self.bRunPostHocTest = False
		
	def mouseEventCallback(self, callback):
		if self.cid != None:
			FigureCanvas.mpl_disconnect(self, self.cid)
			
		self.cid = FigureCanvas.mpl_connect(self, 'button_press_event', callback)
			
	def plot(self, profile, statsResults):
		pass
	
	def configure(self, profile, statsResults):
		pass
	
	@mpl14Defaults
	def savePlot(self, filename, dpi=300):
		format = filename[filename.rfind('.')+1:len(filename)]
		if format in ['png', 'pdf', 'ps', 'eps','svg']:
			self.fig.savefig(filename,format=format,dpi=dpi,facecolor='white',edgecolor='white')
		else:
			pass
	
	def clear(self):
		self.fig.clear()
		
	def mirrorProperties(self, plotToCopy):
		self.type = plotToCopy.type
		self.name = plotToCopy.name
		self.bSupportsHighlight = plotToCopy.bSupportsHighlight
	
	def labelExtents(self, xLabels, xFontSize, xRotation, yLabels, yFontSize, yRotation):
		self.fig.clear()
		
		tempAxes = self.fig.add_axes([0,0,1.0,1.0])	
		
		tempAxes.set_xticks(np.arange(len(xLabels)))	
		tempAxes.set_yticks(np.arange(len(yLabels)))	
		
		xText = tempAxes.set_xticklabels(xLabels, size=xFontSize, rotation=xRotation)
		yText = tempAxes.set_yticklabels(yLabels, size=yFontSize, rotation=yRotation)
		
		bboxes = []
		for label in xText:
			bbox = label.get_window_extent(self.get_renderer())
			bboxi = bbox.transformed(self.fig.transFigure.inverted())
			bboxes.append(bboxi)
		xLabelBounds = mtransforms.Bbox.union(bboxes)
		
		bboxes = []
		for label in yText:
			bbox = label.get_window_extent(self.get_renderer())
			bboxi = bbox.transformed(self.fig.transFigure.inverted())
			bboxes.append(bboxi)		
		yLabelBounds = mtransforms.Bbox.union(bboxes)			
		
		self.fig.clear()
		
		return xLabelBounds, yLabelBounds
		
	def xLabelExtents(self, labels, fontSize, rotation=0):
		self.fig.clear()
		
		tempAxes = self.fig.add_axes([0,0,1.0,1.0])	
		tempAxes.set_xticks(np.arange(len(labels)))	
		xLabels = tempAxes.set_xticklabels(labels, size=fontSize, rotation=rotation)
		
		bboxes = []
		for label in xLabels:
			bbox = label.get_window_extent(self.get_renderer())
			bboxi = bbox.transformed(self.fig.transFigure.inverted())
			bboxes.append(bboxi)		
		xLabelBounds = mtransforms.Bbox.union(bboxes)		
		
		self.fig.clear()
		
		return xLabelBounds
	
	def yLabelExtents(self, labels, fontSize, rotation=0):
		self.fig.clear()

		tempAxes = self.fig.add_axes([0,0,1.0,1.0])	
		tempAxes.set_yticks(np.arange(len(labels)))	
		yLabels = tempAxes.set_yticklabels(labels, size=fontSize, rotation=rotation)
		
		bboxes = []
		for label in yLabels:
			bbox = label.get_window_extent(self.get_renderer())
			bboxi = bbox.transformed(self.fig.transFigure.inverted())
			bboxes.append(bboxi)		
		yLabelBounds = mtransforms.Bbox.union(bboxes)		
		
		self.fig.clear()
		
		return yLabelBounds

	@mpl14Defaults
	def emptyAxis(self, title = ''):
		self.fig.clear()
		self.fig.set_size_inches(6,4)	
		emptyAxis = self.fig.add_axes([0.1,0.1,0.8,0.8]) 
		
		emptyAxis.set_ylabel('No active features or degenerate plot', fontsize=8)
		emptyAxis.set_xlabel('No active features or degenerate plot', fontsize=8)
		emptyAxis.set_yticks([])
		emptyAxis.set_xticks([])
		emptyAxis.set_title(title)
		
		for loc, spine in emptyAxis.spines.items():
			if loc in ['right','top']:
					spine.set_color('none') 
		
		self.updateGeometry()
		self.draw()
		
	def formatLabels(self, labels): 
		formattedLabels = []     
		for label in labels: 
			value = float(label.get_text())    
			if value < 0.01:
				valueStr = '%.2e' % value
				if 'e-00' in valueStr:
					valueStr = valueStr.replace('e-00', 'e-')
				elif 'e-0' in valueStr:
					valueStr = valueStr.replace('e-0', 'e-')
			else:
				valueStr = '%.3f' % value
				
			formattedLabels.append(valueStr)
				
		return formattedLabels
	
class ConfigureDialog(QtWidgets.QDialog):
	def __init__(self, configDialogUI, parent=None):
		QtWidgets.QDialog.__init__(self, parent)
		
		# initialize GUI
		self.ui = configDialogUI()
		self.ui.setupUi(self)

		self.centerWindow()

	def centerWindow(self):
		screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
		size =	self.geometry()
		self.move((screen.width()-size.width())//2, (screen.height()-size.height())//2)
	
class TestWindow(QtWidgets.QMainWindow):
	'''
	Simple Qt window for testing plots.
	'''
	
	def __init__(self, PlotClass, statsResults = ''):
		'''
		Create window with plot.
		PlotClass - a class object (not instance) inherited from AbstractPlotPlugin
		'''
		
		QtWidgets.QMainWindow.__init__(self)
		self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
		self.setWindowTitle("Test Window")
		
		self.main_widget = QtWidgets.QWidget(self)
		
		layout = QtWidgets.QVBoxLayout(self.main_widget)
		testPlot = PlotClass(self.main_widget)
		
		if statsResults != '':
			testPlot.plot(statsResults)
		else:
			testPlot.emptyAxis()
		layout.addWidget(testPlot)
		
		self.main_widget.setFocus()
		self.setCentralWidget(self.main_widget)
				