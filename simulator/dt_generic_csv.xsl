<?xml version="1.0" encoding="UTF-8"?>
<!-- dt_generic_csv.xsl: Document Transformation default - flattens any
     connector XML (one record element per row) into CSV. -->
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="text"/>
  <xsl:template match="/">
    <xsl:for-each select="/*/*[1]//*[not(*)]">
      <xsl:value-of select="local-name()"/>
      <xsl:if test="position() != last()">,</xsl:if>
    </xsl:for-each>
    <xsl:text>&#10;</xsl:text>
    <xsl:for-each select="/*/*">
      <xsl:for-each select=".//*[not(*)]">
        <xsl:value-of select="normalize-space(.)"/>
        <xsl:if test="position() != last()">,</xsl:if>
      </xsl:for-each>
      <xsl:text>&#10;</xsl:text>
    </xsl:for-each>
  </xsl:template>
</xsl:stylesheet>
