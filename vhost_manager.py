import json
import re
import os

def prep_value(key, value, indent = False):
    if type(value) == list:
        return ''.join([ prep_value(key, item, indent) for item in value ])
    if indent: key = '  ' + key
    return '%s%s%s\n' % (key, ' ' * max(1, 26 - len(key)), value)

def export_obj(name, obj):
    props = ''.join([ prep_value(key, value, True) for key, value in obj.items() ])
    return '%s {\n%s}\n\n' % (name, props)

class HTTPD:
    def __init__(self, lsws_path = '/usr/local/lsws/'):
        self.configs = {
            'general': {},
            'virtualhosts': {},
            'listeners': {}
        }
        self.block = self.configs['general']
        self.lsws_path = lsws_path
        self.httpd_config = open('%s/conf/httpd_config.conf' % lsws_path).readlines()

    def set_block(self, line):
        line = line[:-2]
        key, *args = line.split()
        
        if key == 'virtualhost':
            self.configs['virtualhosts'][args[0]] = {}
            self.block = self.configs['virtualhosts'][args[0]]
            return

        if key == 'listener':
            self.configs['listeners'][args[0]] = {'mapping': {}}
            self.block = self.configs['listeners'][args[0]]
            return
        
        self.configs['general'][line] = {}
        self.block = self.configs['general'][line]


    def unset_block(self):
        self.block = self.configs['general']

    def add_prop(self, line):
        key, value = line.split(' ', 1)
        if key == 'map' and 'mapping' in self.block:
            vhost, urls = value.split(' ', 1)
            self.block['mapping'][vhost] = urls.split(', ')
            return

        if key in self.block:
            if type(self.block[key]) == list:
                self.block[key].append(value)
            else:
                self.block[key] = [ self.block[key], value ]
        else:
            self.block[key] = value

    def parse_file(self):
        for line in self.httpd_config:
            clean_line = ' '.join(line.split())
            if len(clean_line) == 0: continue
            if clean_line.endswith('{'): self.set_block(clean_line); continue
            if clean_line.endswith('}'): self.unset_block(); continue
            self.add_prop(clean_line)

    def gen_file(self, output = '/usr/local/lsws/conf/httpd_config.conf'):
        output = open(output, 'w+')
        
        #write general settings
        for key, value in self.configs['general'].items():
            if type(value) == str: output.write(prep_value(key, value))

        output.write('\n')

        for key, value in self.configs['general'].items():
            if type(value) == dict: output.write(export_obj(key, value))

        #write vhosts
        for key, value in self.configs['virtualhosts'].items():
            output.write(export_obj('virtualhost %s' % key, value))
        
        #write listeners
        for listener, props in self.configs['listeners'].items():
            props_str = ''.join([ prep_value(key, value, True) for key, value in props.items() if type(value) == str])
            props_str += ''.join([ prep_value('map', '%s %s' % (key, ', '.join(value)), True) for key, value in props['mapping'].items() ])
            output.write('listener %s {\n%s}\n\n' % (listener, props_str))

        output.close()


def parse_path(path, VARS): 
    return os.path.normpath(re.sub(r'\$([A-Z_]+)', lambda x: VARS[x[1]], path))

def setup_vhost(httpd, vhost_name, vhost_root, vhost_doc_root, vhost_domains, create_index_file = False):
    VARS = {
        'SERVER_ROOT': httpd.lsws_path,
        'VH_NAME': vhost_name,
        'VH_ROOT': vhost_root,
        'DOC_ROOT': vhost_doc_root
    }

    config_file_dir = parse_path('$SERVER_ROOT/conf/vhosts/$VH_NAME/', VARS)
    config_file_path = parse_path('$SERVER_ROOT/conf/vhosts/$VH_NAME/$VH_NAME.conf', VARS)
    VARS['VH_ROOT'] = parse_path(VARS['VH_ROOT'], VARS)
    VARS['DOC_ROOT'] = parse_path(VARS['DOC_ROOT'], VARS)

    #mk root and doc dir
    if not os.path.exists(VARS['VH_ROOT']): os.makedirs(VARS['VH_ROOT'])
    if not os.path.exists(VARS['DOC_ROOT']): os.makedirs(VARS['DOC_ROOT'])

    #create index file
    if create_index_file:
        index_file = open('%s/index.html' % VARS['DOC_ROOT'], 'w+')
        index_file.write('Hello World!')
        index_file.close()
    
    #mk config dir
    if not os.path.exists(config_file_dir): os.makedirs(config_file_dir)

    #add vhost
    httpd.configs['virtualhosts'][vhost_name] = {
        'vhRoot': vhost_root,
        'configFile': '$SERVER_ROOT/conf/vhosts/$VH_NAME/%s.conf' % (vhost_name),
        'allowSymbolLink': 1,
        'enableScript': 1,
        'restrained': 1
    }

    #map domain
    for listener in httpd.configs['listeners'].keys():
        httpd.configs['listeners'][listener]['mapping'][vhost_name] = vhost_domains

    #gen vhost config file
    configs = {
        'docRoot': vhost_doc_root,
        'vhDomain': vhost_domains[0],
        'enableGzip': '1',
        'cgroups': '0',
        'context /': {
            'location': '$DOC_ROOT/',
            'allowBrowse': '1',
            'rewrite':  {},
            'addDefaultCharset': 'off',
            'phpIniOverride': {}
        }
    }

    config_file = open(config_file_path, 'w+')

    for key, value in configs.items():
        if type(value) == str: config_file.write(prep_value(key, value))
        if type(value) == dict: config_file.write(export_obj(key, value))
    config_file.close()


#HTTPD(lsws_path)
httpd = HTTPD()
httpd.parse_file()

#setup as many vhosts as you want
sites = [ 'example.site', 'example.net' ]
for site in sites:
    setup_vhost(httpd, site, '$SERVER_ROOT/sites/%s/' % site, '$VH_ROOT/public/', [ site ], True)

#httpd.gen_file(output_file)
httpd.gen_file()