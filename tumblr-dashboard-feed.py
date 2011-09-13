import os
import time
import logging
import httplib, urllib
from StringIO import StringIO
from ConfigParser import RawConfigParser
from feedformatter import Feed
try:
  from xml.etree.cElementTree import XML
except ImportError:
  from xml.etree.ElementTree import XML

###########################
# Setup (config, logging) #
###########################
_defaults = {
  'LOGGING': False,
  'tumblr': {
             'email': 'example@example.com',
             'password': 'example',
            },
  'feed': {
           'title': 'My Dashboard Feed',
           'description': 'My Tumblr Dashboard feed',
           'img_size': 0,
          },
            }

_config = RawConfigParser(_defaults)
_config.read('config.ini')
_log_kw = {'filename': 'tumblr-dashboard-feed.log',
           'format':'[%(asctime)s %(levelname)s] %(message)s',
           'datefmt':'%Y-%m-%d %H-%M-%S'}

if _config.get('DEFAULT','LOGGING'):
  logging.basicConfig(level=logging.DEBUG,**_log_kw)
else:
  logging.basicConfig(level=logging.CRITICAL,**_log_kw)

#############
# Functions #
#############
def fetch_tumblr_dashboard_xml(email,password):
  """Implements a Tumblr Dashboard API read
  
  :param string email: Tumblr account email address
  :param string password: tumblr account password
  """
  
  logging.debug('Requesting API read')
  
  # Prepare POST request
  params = urllib.urlencode([('email',email),('password',password),
                             ('generator','Tumblr Dashboard Reader'),
                             ('num','50')])
  headers = {"Content-type": "application/x-www-form-urlencoded",
             "Accept": "text/plain"}
  
  connection = httplib.HTTPConnection("www.tumblr.com")
  connection.request("POST", "/api/dashboard", params,headers)
  response = connection.getresponse()
  connection.close()
  
  if str(response.status) == '200':
    return response.read()
  else:
    logging.error('Connection failed. Response %s, %s' % (response.status, response.reason))
    return None

def xml_to_atom(xml,feedtitle,feeddescription,feedurl,authoremail,img_size=0):
  """Transform the XML from Tumblr into an Atom feed.
  
  :param string xml: Raw XML returned from Tumblr
  :param string feedtitle: Title of the atom feed
  :param string feeddescription: Description of the atom feed
  :param string feedurl: URL that will contain the feed
  :param int img_size: Size of images to include; 0-5 (0 is original, 5 is small)
  :returns: The Atom feed's XML
  """
  # Make sure parameters are "good"
  if feedurl.endswith('atom.xml'):
    pass
  elif feedurl[-1] == '/':
    feedurl = feedurl+'atom.xml'
  else:
    feedurl = feedurl+'/atom.xml'
  
  if type(img_size) is not int:
    img_size = int(img_size)
  
  # Set up the Atom feed
  atom = Feed()
  atom.feed["title"] = feedtitle
  atom.feed["description"] = feeddescription
  atom.feed["id"] = feedurl
  atom.feed["link"] = {'_href': feedurl,
                       '_rel': 'self',
                       '_type': 'application/atom+xml'}
  atom.feed["generator"] = {'_uri': "http://github.com/tbekolay/Tumblr-Dashboard-Feed",
                            '_version': '0.1',
                            'text': 'Tumblr Dashboard Reader'}
  atom.feed["icon"] = "http://assets.tumblr.com/images/favicon.gif"
  atom.feed["logo"] = "http://assets.tumblr.com/images/logo.png"
  atom.feed["author"] = {'name':authoremail.split('@')[0], 'email':authoremail}
  atom.feed["updated"] = time.gmtime()
  
  # Start parsing the XML file
  et = XML(xml)
  posts = et.find('posts')
  
  for post in posts.findall('post'):
    # Information common to all types
    item = {}
    item["id"] = post.attrib.get('url-with-slug')
    item["link"] = {'_href': post.attrib.get('url-with-slug'),
                    '_rel': 'alternate',
                    '_type': 'text/html'}
    date = time.strptime(post.attrib.get('date-gmt'),"%Y-%m-%d %H:%M:%S %Z") #2011-09-12 00:33:28 GMT
    item["published"] = date
    item["updated"] = date
    author = post.find('tumblelog')
    shortname = author.attrib.get('name')
    item["author"] = {'name': author.attrib.get('title')+" ("+shortname+")",
                      'uri': author.attrib.get('url')}
    posttype = post.attrib.get('type')
    
    # Make the summary, based on type
    if posttype == "regular":
      item["summary"] = shortname+" posted on Tumblr"
    elif posttype == "answer":
      item["summary"] = shortname+" posted an "+posttype
    elif posttype == "audio":
      item["summary"] = shortname+" posted "+posttype
    else:
      item["summary"] = shortname+" posted a "+posttype
    
    # Get title and content based on type
    content = StringIO()
    #### regular ####
    if posttype == "regular":
      if post.find('regular-title') is None:
        item["title"] = item["summary"]
      else:
        item["title"] = post.find('regular-title').text
      
      if post.find('regular-body') is None:
        content.write(item["title"])
        item["title"] = item["summary"]
      else:
        content.write(post.find('regular-body').text)
    #### link ####
    elif posttype == "link":
      item["title"] = item["summary"]
      
      if post.find('link-title') is None:
        title = post.find('link-url').text
      else:
        title = post.find('link-text').text
      
      if post.find('link-description') is None:
        description = "<p>(No description)</p>"
      else:
        description = post.find('link-description').text
      
      content.write('<a href="%(url)s">%(title)s</a>:%(description)s' % \
                    {'url':post.find('link-url').text,
                     'title':title,
                     'description':description})
    #### quote  ####
    elif posttype == "quote":
      item["title"] = item["summary"]
      
      if post.find('quote-source') is None:
        source = ""
      else:
        source = "<p>&mdash;"+post.find('quote-source').text+"</p>"
      
      content.write('<p>%(text)s</p>%(source)s' % \
                    {'text': post.find('quote-text').text,
                     'source': source})
    #### photo  ####
    elif posttype == "photo":
      item["title"] = item["summary"]
      
      photo_urls = []
      photo_captions = {}
      
      if post.find('photoset') is not None:
        # NOTE: getiterator depricated in 2.7, use iter instead!!
        for photo in post.find('photoset').getiterator('photo'):
          url = photo.findall('photo-url')[img_size].text
          
          if photo.find('photo-caption') is not None:
            photo_captions[url] = photo.find('photo-caption').text
          photo_urls.append(url)
      
      else:
        url = post.findall('photo-url')[img_size].text
        
        if post.find('photo-caption') is not None:
          photo_captions[url] = post.find('photo-caption').text
        photo_urls.append(url)
      
      for url in photo_urls:
        content.write('<img src="%s" /><br />' % url)
        if photo_captions.has_key(url):
          content.write(photo_captions[url])
    #### conversation ####
    elif posttype == "conversation":
      if post.find('conversation-title') is not None:
        item["title"] = post.find('conversation-title').text
      else:
        item["title"] = item["summary"]
      
      for line in post.find('conversation').getiterator('line'):
        content.write("<p><strong>%(label)s</strong> %(text)s" % \
                      {'label': line.attrib.get('label'),
                       'text': line.text})
    #### video ####
    elif posttype == "video":
      item["title"] = item["summary"]
      
      if post.find('video-caption') is not None:
        caption = post.find('video-caption').text
      else:
        caption = ""
      
      content.write("%(player)s%(caption)s" % \
                    {'player': post.find('video-player').text,
                     'caption': caption})
    #### audio ####
    elif posttype == "audio":
      item["title"] = item["summary"]
      
      if post.find('audio-caption') is not None:
        caption = post.find('audio-caption').text
      else:
        caption = ""
      
      content.write("%(player)s%(caption)s" % \
                    {'player': post.find('audio-player').text,
                     'caption': caption})
    #### answer ####
    elif posttype == "answer":
      item["title"] = item["summary"]
      
      content.write(
        "<p><strong>Question</strong></p><p>%(question)s</p><p><strong>Answer</strong></p>%(answer)s" % \
        {'question': post.find('question').text,
         'answer': post.find('answer').text})
    
    # Get reblog information, since that's, you know, kind of important
    if post.attrib.has_key('reblogged-from-name'):
      content.write('<p><em>reblogged from <a href="%(url)s">%(name)s</a></em></p>' % \
                    {'url': post.attrib.get('reblogged-from-url'),
                     'name': post.attrib.get('reblogged-from-name')})
    
    # Get tag information
    if post.find('tag') is not None:
      url = post.find('tumblelog').attrib.get('url')
      content.write('<p><strong>Tags:</strong>')
      for tag in post.getiterator('tag'):
        text = tag.text
        content.write(' <a href="%(tagurl)s">#%(text)s</a>' % \
                      {'tagurl': url+'tagged/'+text,
                       'text': text})
      content.write('</p>')
    
    item["content"] = content.getvalue()
    content.close()
    atom.items.append(item)
  
  return atom.format_atom_string(pretty=True)

########################
# Non-import behaviour #
########################
if __name__ == '__main__':
  xml_path = 'tumblr.xml'
  atom_path = 'atom.xml'
  
  xml = fetch_tumblr_dashboard_xml(_config.get('tumblr','email'),_config.get('tumblr','password'))
  
  if xml is None:
    # Fallback to reading an old tumblr.xml
    with open(xml_path,'r') as f:
      xml = ''.join(f.readlines())
  else:
    # Write raw data to tumblr.xml just in case
    with open(xml_path,'w') as f:
      f.writelines(xml)

  atom = xml_to_atom(xml,_config.get('feed','title'),
                         _config.get('feed','description'),
                         _config.get('feed','url'),
                         _config.get('tumblr','email'),
                         int(_config.get('feed','img_size')))
  
  with open(atom_path,'w') as f:
    f.writelines(atom)

