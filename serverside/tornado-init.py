#!/usr/bin/python2.6


import tornado.ioloop
import tornado.web
import tornado.websocket

import config


from module_manager import DriveSuggest, DriveSearch, LoadModules, DriveTags, DriveRelevance, DriveAPIKeys
from xml.dom.minidom import Document
import os

#statically loading modules
w = LoadModules()

#this is IOloop instance we would use to push data to client
ioloop_instance = tornado.ioloop.IOLoop.instance()


from xml.dom.minidom import parse, parseString
from xml.parsers.expat import ExpatError
from time import sleep
#import thread
from threading import Thread


class ParseAndExec(object):
    '''
    It parses the XML send from clients , parses it and then executes whats possible it accordingly
    '''

    NONODE = 600
    NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED = 601
    NODE_TYPE_UNKNOWN = 602
    PROPERTY_VALUE_UNKNOWN = 603
    NODE_UNKNOWN = 604

    def __init__(self, xml, websocketHandler):
        self.xml = xml.encode('utf-8')
        self.websocketHandler = websocketHandler

    def handleError(self, errorCode):
        self.websocketHandler.write_message( u'<?xml version="1.0" ?> <error code="' + str(errorCode) + '">' )

    def go(self):
        '''
        This is time cosuming funtion, it takes modules times each http call to return data (calls go_module [which takes time to run] modules times)
        '''
 
        def go_module(data, module, driveFunction):
            '''
            'go' for each module | time taking funtion. runs in seperate thread
            '''

            s = driveFunction(w, data, returntype = 'xml', module = module)
            result = s.result()
            if not result is None:
               #data flushes out immedietly
               self.websocketHandler.write_message( result )

        dom = ''
        try:
            dom = parseString(self.xml)
        except ExpatError as err:
            if err.code == 3:
                self.handleError( self.NONODE )
                return
            
        self.nodes = dom.childNodes
        if len(self.nodes) == 0:
            self.handleError( self.NONODE )
            return

        if len( self.nodes[0].childNodes ) == 0:
            self.handleError( self.NONODE ) # or what?
            return

        nodeName = self.nodes[0].nodeName 


        api = ""
        try:
            api = self.nodes[0].attributes["api"].value
        
            try:
                is_api = DriveAPIKeys().is_api(api)
                if is_api == False:
                    self.handleError( DriveAPIKeys.WRONG_API ) 
                    return
                #by this line.. its proved to be right api
            except:
                pass

        except:
            self.handleError( self.NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED )
            return



        if nodeName == u"query":
            nodeAttribute = ""
            try:
                nodeAttribute = self.nodes[0].attributes["type"].value
            except:
                self.handleError( self.NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED )
                return
                
            if nodeAttribute == u"suggest":
                data = self.nodes[0].childNodes[0].data
                
                for i in range(len(w.suggestModules)):
                    #this is non blocking as it makes each module run in seperate thread
                    t = Thread(target=go_module, args=(data, w.suggestModules[i], DriveSuggest))
                    t.start()

            elif nodeAttribute == u"search":
                data = self.nodes[0].childNodes[0].data
                
                for i in range(len(w.searchModules)):
                    #this is non blocking as it makes each module run in seperate thread
                    t = Thread(target=go_module, args=(data, w.searchModules[i], DriveSearch))
                    t.start()

            else:
                self.handleError( self.NODE_TYPE_UNKNOWN )
                return
            
        elif nodeName == u"tagService":
            nodeAttribute_type = ""
            nodeAttribute_imageid = ""
            try:
                nodeAttribute_type = self.nodes[0].attributes["type"].value
                nodeAttribute_imageid = self.nodes[0].attributes["imageid"].value
                try:
                    nodeAttribute_imageid = int(nodeAttribute_imageid)
                except:
                    self.handleError( self.TYPE_MISMATCH )
            except:
                self.handleError( self.NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED )
                return
                
            if nodeAttribute_type == u"add":
                tag = self.nodes[0].childNodes[0].data
                driver = DriveTags( tag, 'xml' )
                result = driver.create(nodeAttribute_imageid)
                self.websocketHandler.write_message( result )
                
        elif nodeName == u"relevanceService":
            nodeAttribute_type = ""
            nodeAttribute_imageid = ""
            try:
                nodeAttribute_type = self.nodes[0].attributes["type"].value
                nodeAttribute_imageid = self.nodes[0].attributes["imageid"].value
                try:
                    nodeAttribute_imageid = int(nodeAttribute_imageid)
                except:
                    self.handleError( self.TYPE_MISMATCH )
            except:
                self.handleError( self.NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED )
                return
                
            tag = self.nodes[0].childNodes[0].data #tag means tag id here
            try:
                tag = int(tag)
            except:
                pass
                #because use can also send in tag as unicode

            if nodeAttribute_type == "increase":
                driver = DriveRelevance( tag, nodeAttribute_imageid, 'xml' )
                result = driver.increase()
            elif  nodeAttribute_type == "decrease":
                driver = DriveRelevance( tag, nodeAttribute_imageid, 'xml' )
                result = driver.decrease()
            elif  nodeAttribute_type == "custom":
                try:                    
                    value_to_change = self.nodes[0].attributes["value"].value
                except:
                    self.handleError( self.NODE_COMPLUSORY_ATTRIB_NOT_SPECIFIED )

                try:
                    #this is validation of what user enterd as value .. should  be int with sign
                    validator = (value_to_change[0] == "-" or value_to_change[0] == "+") and int(value_to_change)
                    if validator == False: raise
                    #this means its for changing the value (incrementing or decrementing..not the absolute change)
                except:
                    try:
                        int(value_to_change)
                    except:
                        self.handleError( self.PROPERTY_VALUE_UNKNOWN )
                        return

                    driver = DriveRelevance( tag, nodeAttribute_imageid, 'xml' )
                    result = driver.set( int(value_to_change) )
                    return
                
                driver = DriveRelevance( tag, nodeAttribute_imageid, 'xml' )
                result = driver.change( int(value_to_change[1:]), value_to_change[0] )

            else:
                self.handleError( self.PROPERTY_VALUE_UNKNOWN )
                return
            self.websocketHandler.write_message( result )

        else:
            self.handleError( self.NODE_UNKNOWN )


class WebSocketManager(tornado.websocket.WebSocketHandler):
    def open(self):
        #print "WebSocket opened"
        self.write_message( u'<?xml version="1.0" ?> <notice message="waiting for input" / >' )

    @tornado.web.asynchronous
    def on_message(self, message):
        d = ParseAndExec(message, self)
        d.go()
        #self.finish()
        
    def on_close(self):
        #print "WebSocket closed"
        pass


settings = {
    "static_path": os.path.join(os.path.dirname(__file__), "web"),
}


from apitornado import Newkey, Allkeys, Deletekeys
from relevancetornado import RelevanceTrend
from CCCreator import CCCreator

application = tornado.web.Application([
    (r"/", tornado.web.RedirectHandler, {"url": os.path.join(os.path.dirname(__file__), "index.htm")}),
    (r"/Socket", WebSocketManager),
    # urls of these should not be changed because they have been statically refered in html pages
    (r"/newkey", Newkey),
    (r"/allkeys", Allkeys),
    (r"/delkey", Deletekeys),
    (r"/CCCreator", CCCreator),
    (r"/RelevanceTrend", RelevanceTrend),

    (r"/(.*)", tornado.web.StaticFileHandler, {"path": os.path.join(os.path.dirname(__file__), "web")}),
], **settings)

from tornado.options import define, options

if __name__ == "__main__":
    tornado.options.log_file_prefix = "NOPSA" #loggin issues not resolved yet
    tornado.options.parse_command_line()
    application.listen(config.tornado_port)
    ioloop_instance.start() 


