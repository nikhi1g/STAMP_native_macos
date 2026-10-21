from setuptools import setup

pluginPkgs = []
pluginPkgs.append('stamp.plugins')
pluginPkgs.append('stamp.plugins.common')
pluginPkgs.append('stamp.plugins.common.multipleComparisonCorrections')
pluginPkgs.append('stamp.plugins.groups')
pluginPkgs.append('stamp.plugins.groups.effectSizeFilters')
pluginPkgs.append('stamp.plugins.groups.plots')
pluginPkgs.append('stamp.plugins.groups.plots.configGUI')
pluginPkgs.append('stamp.plugins.groups.statisticalTests')
pluginPkgs.append('stamp.plugins.multiGroups')
pluginPkgs.append('stamp.plugins.multiGroups.effectSizeFilters')
pluginPkgs.append('stamp.plugins.multiGroups.plots')
pluginPkgs.append('stamp.plugins.multiGroups.plots.configGUI')
pluginPkgs.append('stamp.plugins.multiGroups.postHoc')
pluginPkgs.append('stamp.plugins.multiGroups.statisticalTests')
pluginPkgs.append('stamp.plugins.samples')
pluginPkgs.append('stamp.plugins.samples.effectSizeFilters')
pluginPkgs.append('stamp.plugins.samples.plots')
pluginPkgs.append('stamp.plugins.samples.plots.configGUI')
pluginPkgs.append('stamp.plugins.samples.statisticalTests')
pluginPkgs.append('stamp.plugins.samples.confidenceIntervalMethods')

metagenomicPkgs = []
metagenomicPkgs.append('stamp.metagenomics')
metagenomicPkgs.append('stamp.metagenomics.fileIO')
metagenomicPkgs.append('stamp.metagenomics.simulations')
metagenomicPkgs.append('stamp.metagenomics.stats')
metagenomicPkgs.append('stamp.metagenomics.stats.CI')
metagenomicPkgs.append('stamp.metagenomics.stats.distributions')
metagenomicPkgs.append('stamp.metagenomics.stats.empiricalTests')
metagenomicPkgs.append('stamp.metagenomics.stats.tests')

root_files = [('.', ['LICENSE.txt']),
                  ('./manual', ['./manual/STAMP_Users_Guide.pdf']),
                  ('.', ['README.md'])]
setup(
    name='STAMP',
    version='2.1.3',
    author='Donovan Parks, Rob Beiko',
    author_email='donovan.parks@gmail.com',
    packages=['stamp', 'stamp.GUI'] + pluginPkgs + metagenomicPkgs,
    package_data={'stamp': ['data/*.txt']},
    scripts=['bin/STAMP', 'scripts/checkHierarchy.py'],
    license='LICENSE.txt',
    url='http://pypi.python.org/pypi/stamp/',
    description='A graphical software package for analyzing taxonomic and functional profiles.',
    data_files = root_files,
    long_description=open('README.md', encoding='utf-8').read(),
    python_requires=">=3.12",
    install_requires=[
        "PyQt6 >= 6.7",
        "numpy >= 2.0",
        "scipy >= 1.14",
        "matplotlib >= 3.9",
        "biom-format >= 2.1.15",],
)
