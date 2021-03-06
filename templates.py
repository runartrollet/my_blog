#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""myBlog, an assignment on Udacity (Full Stack)."""

# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from math import ceil
import datetime
import jinja2
import webapp2
import verify_signup
from google.appengine.ext.db import BadValueError  # noqa
from hash_functions import make_secure_val, check_secure_val
from Entities import CommentsEntity, BlogEntity, UserEntity, blog_key
import myExceptions
# import test_data

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_dir),
    autoescape=True
)


def _jinja2_filter_datetime(date, myformat='medium'):
    if myformat == 'medium':
        timeformat = '%b %d, %Y %H:%M'
    return date.strftime(timeformat)


jinja_env.filters['datetime'] = _jinja2_filter_datetime


class Handler(webapp2.RequestHandler):
    """Handler for the different landingpages."""

    def write(self, *a, **kw):
        """Web response."""
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):  # noqa
        """Renders into a template."""
        t = jinja_env.get_template(template)
        return t.render(params)

    def render(self, template, **kw):
        """Helper function for rendering templates."""
        username = self.read_secure_cookie('user')
        kw['signed_in'] = username
        kw['user'] = UserEntity.by_name(username)
        self.write(self.render_str(template, **kw))

    def set_cookie(self, name, value, expiration=None):
        """Create a cookie."""
        expireTime = None
        if expiration is not None:
            expireTime = (datetime.datetime.now() +
                          datetime.timedelta(days=expiration))
        self.response.set_cookie(name,
                                 value,
                                 expires=expireTime,
                                 path='/')

    def set_secure_cookie(self, name, value, expires=None):
        """Create a secure cookie in the browser."""
        value = make_secure_val(str(value))
        self.set_cookie(name, value, expires)

    def read_cookie(self, name):
        """Read a cookie from the browser."""
        return self.request.cookies.get(name)

    def read_secure_cookie(self, name):
        """Read a secure cookie from the browser."""
        cookie_value = self.read_cookie(name)
        return cookie_value and check_secure_val(cookie_value)

    def delete_cookie(self, name):
        """Delete a cookie from the browser."""
        self.set_cookie(name,
                        'deleted',
                        -999)

    def perform_login(self, username, expires=None):
        """Set the user-cookie in the browser and redirect."""
        self.set_secure_cookie('user', username, expires)

        self.redirect("/thanks?redirect=/welcome")

    def initialize(self, *a, **kw):
        """Retrieve the user-cookier on every new page-load."""
        webapp2.RequestHandler.initialize(self, *a, **kw)
        username = self.read_secure_cookie('user')
        if username:
            self.user = UserEntity.by_name(username)  # noqa
        else:
            self.user = False  # noqa

    def render_blog_article(self, blog_entry, **kw):
        """Render an html-element for a single blog-entry."""
        self._render_text = blog_entry.article.replace('\n', '<br>')  # noqa
        kw['user_owns_post'] = (self.user and self.user.key().id() ==
                                blog_entry.created_by.key().id())
        kw['user_upvoted'] = self.user and blog_entry.getVotesFromUser(
            self.user) == 'up'
        kw['user_downvoted'] = self.user and blog_entry.getVotesFromUser(
            self.user) == 'down'
        return self.render_str("view_blog_entry.html",
                               blog_entry=blog_entry, **kw)

    def edit_post(self, blog_entry, title, article):
        """Edit a post."""
        if (blog_entry and self.user):
            if title and article:
                try:
                    blog_entry.edit_blog_entry(created_by=self.user,
                                               title=title,
                                               article=article)
                    self.redirect('/blogs/%s' %
                                  str(blog_entry.key().id()))
                except myExceptions.NotUnique:
                    self.render_this(blog_entry=blog_entry,
                                     title=title,
                                     article=article,
                                     error_notUnique=True)
                except myExceptions.EditOthersPosts:
                    self.redirect(
                        '/error?error=NotValidBlogUser')
            else:
                self.render_this(title=title, article=article,
                                 error_missing_fields=True)
        else:
            self.redirect(
                '/error?error=NotValidBlogUser')

    def delete_post(self, blog_entry):
        """Delte a blog_post."""
        if blog_entry:
            try:
                blog_entry.delete_post(self.user)
                self.redirect('/blogs')
            except myExceptions.EditOthersPosts:
                self.redirect(
                    '/error?error=NotValidBlogUser')

    def blog_comment(self,
                     comment,
                     blog_entry,
                     comment_id,
                     delete_comment,
                     redirect):
        """Handle blog comments."""

        comment_entry = CommentsEntity.get_by_id_str(comment_id)

        if comment_entry and blog_entry:
            if comment_entry.commentOn.key().id() == blog_entry.key().id():
                if comment_entry.commentBy.key().id() == self.user.key().id():
                    if delete_comment:
                        # Delete comment
                        comment_entry.delete()
                    else:
                        # Edit comment
                        comment_entry.edit_comment(comment, self.user)
                    self.render("/thanks.html", redirect=redirect)
        elif blog_entry:
            # New comment
            try:
                blog_entry.add_comment(
                    commentBy=self.user, comment=comment)
                self.render("/thanks.html", redirect=redirect)
            except myExceptions.TooShort as e:
                self.redirect("/error?errorType=TooShort&errorMsg=", e)

    def blog_comment_or_vote(self, redirect):
        """Comment or vote on a blog_post."""

        voteType = self.request.get("voteDirection")
        comment_id = self.request.get("comment_id")
        comment = self.request.get("comment").strip()
        delete_comment = self.request.get("delete_comment")
        blog_id = self.request.get("blog_id")
        blog_entry = BlogEntity.get_by_id_str(blog_id)
        if voteType and blog_entry:
            try:
                blog_entry = BlogEntity.get_by_id_str(blog_id)
                blog_entry.vote(voteBy=self.user, voteType=voteType)
                self.render("/thanks.html", redirect=redirect)
            except myExceptions.VoteOnOwnPostNotAllowed:
                self.redirect("/error?errorType=VoteOnOwnPostNotAllowed")
            except BadValueError:
                self.redirect("/error?errorType=BadValueError")
        elif comment and blog_entry:
            self.blog_comment(comment,
                              blog_entry,
                              comment_id,
                              delete_comment,
                              redirect)
        elif blog_entry:
            self.redirect("/error?errorType=TooShort")
        else:
            self.redirect("/error?errorType=unknoswn")


class Welcome(Handler):
    """Welcome message for user."""

    def get(self):
        """Show the welcome-message with the username."""
        if self.user:
            self.render("/welcome.html", username=self.user.username)
        else:
            self.redirect("/error?errorType=UserNotLoggedIn")


class Thanks(Handler):
    """Redirection page"""

    def get(self):
        """Show the redirection-page."""
        redirect = self.request.get("redirect")
        self.render("/thanks.html", redirect=redirect)


class Blogs(Handler):
    """Show a list of the latest blogs."""

    def post(self):
        """Vote or comment, redirect to thanks-page if valid vote/comment."""
        self.blog_comment_or_vote("/blogs")

    def get(self):
        """Retrieve all the latest blog-entries and render them to user."""
        page_to_show = self.request.get("page")
        if page_to_show.isdigit() and int(page_to_show) > 1:
            page_to_show = int(page_to_show)
        else:
            page_to_show = 1

        limit = 5
        offset = (page_to_show - 1) * limit
        totalArticles = BlogEntity.all().count(1000)
        totalPages = int(ceil(float(totalArticles) / limit))
        articles = BlogEntity.all().order(
            '-created').fetch(limit=limit, offset=offset)

        self.render("blogs.html", articles=articles,
                    parser=self.render_blog_article,
                    pages=totalPages,
                    currentPage=page_to_show)


class BlogPost(Handler):
    """Show a single blog-entry."""

    def post(self, blog_id):
        """Vote or comment, redirect to thanks-page if valid vote/comment."""
        self.blog_comment_or_vote("/blogs/{}".format(blog_id))

    def get(self, blog_id):  # noqa
        """Retrieve the blog-id from the url and show it."""
        blog_entry = BlogEntity.get_by_id_str(blog_id)
        if not blog_entry:
            self.error(404)
            return
        self.render("blog_permalink.html",
                    article=blog_entry,
                    parser=self.render_blog_article)


class NewBlogPost(Handler):
    """View for creating a new post."""

    def render_this(self, title="", article="", **kw):
        """Renders the 'new blog'-form, but only if the user is logged in."""
        if self.user:
            self.render("new_blog_post.html", title=title,
                        article=article, **kw)
        else:
            self.redirect("/login")

    def get(self):
        """Renders the 'new blog'-form, but only if the user is logged in."""
        self.render_this()

    def post(self):
        """Create a blog-entry if logged in and form filled out correcly."""
        if not self.user:
            self.redirect('/login')
        else:
            title = self.request.get("title").strip()
            article = self.request.get("article")
            if title and article and self.user:
                try:
                    a = BlogEntity.create_blog_entry(parent=blog_key(),
                                                     created_by=self.user,
                                                     title=title,
                                                     article=article)
                    self.redirect('/blogs/%s' % str(a.key().id()))
                except myExceptions.NotUnique:
                    self.render_this(
                        title=title, article=article, error_notUnique=True)
            else:
                self.render_this(title=title, article=article,
                                 error_missing_fields=True)


class EditBlogPost(Handler):
    """View for Eediting a post."""

    def render_this(self, blog_entry=None, title="", article="", **kw):
        """Renders the 'edit blog'-form, but only if the user is logged in."""
        if (self.user and blog_entry and
                self.user.key().id() == blog_entry.created_by.key().id()):

            self.render('new_blog_post.html', title=title,
                        article=article, blog_entry=blog_entry, **kw)
        else:
            self.redirect("/error?errorType=NotValidBlogUser")

    def get(self):
        """If blog_id is in url, lookup BlogEntity and pass along"""
        blog_id = self.request.get("blog_id")
        blog_entry = BlogEntity.get_by_id_str(blog_id)
        if blog_entry:
            self.render_this(blog_entry=blog_entry,
                             title=blog_entry.title,
                             article=blog_entry.article)
        else:
            self.render('/error?error=NotValidBlogUser')

    def post(self):
        """Create/edit a blog-entry if logged in and form filled correcly."""
        title = self.request.get("title").strip()
        article = self.request.get("article").strip()

        # If user is editing a post, we should get a blog_id
        blog_id = self.request.get("blog_id")
        blog_entry = BlogEntity.get_by_id_str(blog_id)
        deletePost = bool(self.request.get("delete"))
        deletion_verified = bool(self.request.get("verify_deletion_checkbox"))
        cancel = bool(self.request.get("cancel"))
        if cancel:
            self.redirect('/blogs/%s' % blog_id)
        else:
            if not self.user:
                self.redirect('/login')
            elif deletePost:
                if deletion_verified:
                    self.delete_post(blog_entry)
                else:
                    self.render_this(blog_entry=blog_entry,
                                     title=title,
                                     article=article,
                                     verify_deletion=True)

            else:
                self.edit_post(blog_entry, title, article)


class Login(Handler):
    """Login user."""

    def get(self):
        """View for login-screen."""
        self.render("login.html")

    def post(self):
        """Log in user(set cookie) if user and password matches."""
        username = self.request.get("username")
        password = self.request.get("password")
        remember_me = self.request.get("remember_me")

        valid_login = UserEntity.check_username_password(username, password)

        if valid_login:
            expires = None
            if remember_me:
                expires = 30
            self.perform_login(username, expires)
        else:
            self.render("login.html",
                        error_invalid_login=True,
                        username=username,
                        remember_me=remember_me,
                        )  # noqa


class Logout(Handler):
    """Logout user."""

    def get(self):
        """Delete usercookie to logout user."""
        self.delete_cookie('user')
        self.redirect('/signup')


class SignUp(Handler):
    """View for sign-up-form."""

    def get(self):
        """Show the sign-up-form."""
        self.render("signup.html",
                    username_valid=True,
                    password_valid=True,
                    passwords_matches=True,
                    email_valid=True,
                    )  # noqa

    def post(self):
        """Register the user if form is filled out correctly."""
        username = self.request.get("username")
        email = self.request.get("email")
        password = self.request.get("password")
        verify = self.request.get("verify")

        username_valid = verify_signup.valid_username(username)
        password_valid = verify_signup.valid_password(password)
        passwords_matches = verify_signup.verify_passwords_matches(
            password, verify)
        email_valid = verify_signup.valid_email(email)

        if email == "":
            email_valid = True
        if not(
                username_valid and
                password_valid and
                passwords_matches and
                email_valid):
            self.render("signup.html",
                        error_username_invalid=not username_valid,
                        error_password_invalid=not password_valid,
                        error_passwords_mismatch=not passwords_matches,
                        error_email_invalid=not email_valid,
                        username=username,
                        email=email,
                        )  # noqa
        else:
            try:
                UserEntity.register(username, password, email)
                self.perform_login(username)
            except myExceptions.NotUnique:
                self.render("signup.html",
                            errro_username_already_in_use=True,
                            username=username,
                            email=email,
                            )  # noqa


class Error(Handler):
    """Error page."""

    def get(self):
        """Show errorpage."""
        errorType = self.request.get("errorType")
        redirect = self.request.get("redirect")
        if redirect == "":
            redirect = '/'
        self.render('error.html', errorType=errorType, redirect=redirect)


app = webapp2.WSGIApplication([
    ('/', Blogs),
    ('/signup', SignUp),
    ('/login', Login),
    ('/logout', Logout),
    ('/error', Error),
    ('/thanks', Thanks),
    ('/welcome', Welcome),
    ('/new_blog_post', NewBlogPost),
    ('/blogs', Blogs),
    ('/blogs/(\d+)', BlogPost),  # noqa
    ('/edit_blog_post', EditBlogPost),  # noqa
], debug=True)
