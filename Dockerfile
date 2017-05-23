FROM php:5.6-fpm

# Install composer
RUN curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/bin --filename=composer

# Install package dependencies
RUN apt-get update && apt-get install -y \
    zlib1g \
    zlib1g-dev \
    git \
    libmcrypt-dev \
    libxml2-dev \
    libgmp-dev \
    libpcre3-dev \
    php-apc \
    libicu-dev

#apc is only available in a PECL install so yea
RUN pecl install apcu-4.0.11 \
    && echo extension=apcu.so > /usr/local/etc/php/conf.d/docker-php-ext-apcu.ini

# docker-ext-install isn't checking 64bit lib dir for this...
RUN ln -s /usr/include/x86_64-linux-gnu/gmp.h /usr/include/gmp.h

RUN docker-php-ext-install \
    mysql \
    zip \
    mcrypt \
    soap \
    mysqli \
    gettext \
    gmp \
    sockets \
    intl

# IMPORTANT NOTE:
#   xdebug.remote_connect_back=1 is not working as expected on Docker for Mac
#   See https://forums.docker.com/t/ip-address-for-xdebug/10460/22
#   Workaround: Create an alias for your mac loopback interface
#   > sudo ifconfig lo0 alias 10.254.254.254
#   > Set remote_connect_back=0 below
RUN pecl install xdebug && \
    echo "zend_extension = "`echo "<?php print ini_get('extension_dir');" |php`"/xdebug.so" >> /usr/local/etc/php/php.ini
