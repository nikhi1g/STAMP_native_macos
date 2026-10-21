#=======================================================================
# Author: Donovan Parks
#
# Load plugins.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with STAMP. If not, see <http://www.gnu.org/licenses/>.
#=======================================================================

import importlib
import pkgutil

def loadPluginModules(pluginFolder):
	'''
	Import every plugin module in pluginFolder (given as upstream did, e.g. 'stamp/plugins/samples/plots/')
	and return a list of (module name, module). As upstream, only the folder's own .py files are plugins:
	__init__ and sub-folders are skipped.

	Plugins are found through the imported stamp package rather than the working directory, so this
	works from a checkout and from a frozen (PyInstaller) app.
	ponytail: a frozen app must bundle the plugin modules (e.g. collect_submodules('stamp.plugins')),
	since nothing imports them by name; pkgutil.iter_modules then lists them from the archive.
	'''
	packageName = pluginFolder.strip('/').replace('/', '.')
	package = importlib.import_module(packageName)

	modules = []
	for moduleInfo in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
		if moduleInfo.ispkg:
			continue
		modules.append((moduleInfo.name, importlib.import_module(packageName + '.' + moduleInfo.name)))

	return modules

class PluginManager:
	def __init__(self, preferences):
		self.preferences = preferences
		pass
		
	def loadPlugins(self, pluginFolder):
		d = {}
		for pluginModule, theModule in loadPluginModules(pluginFolder):
			theClass = getattr(theModule, pluginModule)
			theObject = theClass(self.preferences)
			d[theObject.name] = theObject

		return d
	
	def populateComboBox(self, d, comboBox, defaultPlugin):
		keys = list(d.keys())
		keys.sort(key=str.lower)
		for key in keys:
			comboBox.addItem(key)
		comboBox.setCurrentIndex(comboBox.findText(defaultPlugin))
