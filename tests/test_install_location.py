"""Decision rules for the first-run "Move to Applications" prompt (stamp/installLocation.py)."""
import os
import plistlib
import zipfile

from stamp import installLocation as il

HOME = '/Users/someone'


def test_bundle_path():
	assert il.bundlePath('/Users/someone/Downloads/STAMP.app/Contents/MacOS/STAMP') == '/Users/someone/Downloads/STAMP.app'
	assert il.bundlePath('/usr/bin/python3') is None


def test_translocation_detection():
	assert il.isTranslocated('/private/var/folders/x/T/AppTranslocation/ABC/d/STAMP.app')
	assert not il.isTranslocated('/Users/someone/Downloads/STAMP.app')
	assert il.originalPath('/Users/someone/Downloads/STAMP.app') == '/Users/someone/Downloads/STAMP.app'


def test_is_in_applications():
	assert il.isInApplications('/Applications/STAMP.app', HOME)
	assert il.isInApplications('/Applications/Science/STAMP.app', HOME)
	assert il.isInApplications(HOME + '/Applications/STAMP.app', HOME)
	assert not il.isInApplications(HOME + '/Downloads/STAMP.app', HOME)
	assert not il.isInApplications('/Volumes/STAMP 2.1.3/STAMP.app', HOME)
	assert not il.isInApplications('/ApplicationsOld/STAMP.app', HOME)


def test_should_offer():
	assert il.shouldOffer(HOME + '/Downloads/STAMP.app', HOME, doNotOffer=False)
	assert not il.shouldOffer(HOME + '/Downloads/STAMP.app', HOME, doNotOffer=True)    # "don't remind me"
	assert not il.shouldOffer('/Applications/STAMP.app', HOME, doNotOffer=False)
	assert not il.shouldOffer(None, HOME, doNotOffer=False)                            # not a bundle


def test_destination_admin_vs_standard_user():
	assert il.destinationDir(HOME, canWrite=lambda p, m: True) == '/Applications'
	assert il.destinationDir(HOME, canWrite=lambda p, m: False) == HOME + '/Applications'


def test_version_compare(tmp_path):
	def bundle(version):
		b = tmp_path / version / 'STAMP.app' / 'Contents'
		b.mkdir(parents=True, exist_ok=True)
		with open(b / 'Info.plist', 'wb') as f:
			plistlib.dump({'CFBundleShortVersionString': version}, f)
		return str(b.parent)
	assert il.versionKey(il.bundleVersion(bundle('2.1.10'))) > il.versionKey(il.bundleVersion(bundle('2.1.3')))
	assert il.versionKey('2.1.3') == il.versionKey(il.bundleVersion(bundle('2.1.3')))
	assert il.bundleVersion(str(tmp_path / 'missing.app')) == '0'


def test_disk_image_lookup():
	info = plistlib.dumps({'images': [{'image-path': '/Users/someone/Downloads/STAMP-2.1.3.dmg',
		'system-entities': [{'dev-entry': '/dev/disk4'}, {'mount-point': '/Volumes/STAMP 2.1.3'}]}]})
	assert il.diskImageFor('/Volumes/STAMP 2.1.3/STAMP.app', info) == ('/Volumes/STAMP 2.1.3', '/Users/someone/Downloads/STAMP-2.1.3.dmg')
	assert il.diskImageFor('/Volumes/Other/STAMP.app', info) == (None, None)
	assert il.diskImageFor(HOME + '/Downloads/STAMP.app', info) == (None, None)


def test_leftover_zips_only_stamp_downloads(tmp_path):
	def make(name, members):
		with zipfile.ZipFile(tmp_path / name, 'w') as z:
			for m in members:
				z.writestr(m, 'x')
	make('STAMP-2.1.3.zip', ['STAMP.app/Contents/Info.plist'])
	make('STAMP-2.1.3 (1).zip', ['STAMP.app/Contents/Info.plist'])
	make('STAMP-2.1.3-2.zip', ['STAMP.app/Contents/Info.plist'])        # version + build number
	make('STAMP-2.1.3-other.zip', ['STAMP.app/Contents/Info.plist'])    # name does not match
	make('STAMP.zip', ['notes.txt'])                                     # no STAMP.app inside
	make('homework.zip', ['STAMP.app/Contents/Info.plist'])              # not a STAMP download
	(tmp_path / 'STAMP-2.0.zip').write_text('not a zip')                 # unreadable
	found = [os.path.basename(p) for p in il.leftoverZips(str(tmp_path))]
	assert found == ['STAMP-2.1.3 (1).zip', 'STAMP-2.1.3-2.zip', 'STAMP-2.1.3.zip']


def test_existing_target_never_touches_a_different_app(tmp_path):
	def bundle(folder, ident, version):
		c = tmp_path / folder / 'STAMP.app' / 'Contents'
		c.mkdir(parents=True)
		with open(c / 'Info.plist', 'wb') as f:
			plistlib.dump({'CFBundleIdentifier': ident, 'CFBundleShortVersionString': version}, f)
		return str(c.parent)
	source = bundle('downloads', 'com.nikhilgupta.stamp', '2.1.3')
	assert il.existingTargetAction(str(tmp_path / 'empty' / 'STAMP.app'), source) == 'none'
	assert il.existingTargetAction(bundle('older', 'com.nikhilgupta.stamp', '2.1.2'), source) == 'replace'
	assert il.existingTargetAction(bundle('same', 'com.nikhilgupta.stamp', '2.1.3'), source) == 'replace'
	assert il.existingTargetAction(bundle('newer', 'com.nikhilgupta.stamp', '2.2.0'), source) == 'open-existing'
	# e.g. the Porting Kit (Wine) wrapper, also named STAMP.app, at version 1.0
	assert il.existingTargetAction(bundle('wine', 'com.STAMP369632276.wineskin', '1.0'), source) == 'foreign'
