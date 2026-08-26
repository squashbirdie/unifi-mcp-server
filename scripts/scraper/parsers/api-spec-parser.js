/**
 * API Specification Parser
 * Normalizes scraped data into structured API specification format
 */

/**
 * API Specification class
 */
export class APISpecification {
  constructor() {
    this.version = null;
    this.lastUpdated = new Date().toISOString().split('T')[0];
    this.baseUrl = 'https://unifi.ui.com/api';
    this.categories = [];
  }

  /**
   * Set version information
   * @param {string} version - API version
   */
  setVersion(version) {
    this.version = version;
  }

  /**
   * Add a new category
   * @param {string} name - Category name
   * @returns {Object} Category object
   */
  addCategory(name) {
    // Check if category already exists
    let category = this.categories.find(c => c.name === name);

    if (!category) {
      category = {
        name,
        endpoints: []
      };
      this.categories.push(category);
    }

    return category;
  }

  /**
   * Add an endpoint to a category
   * @param {string} categoryName - Category name
   * @param {Object} endpointData - Endpoint data
   */
  addEndpoint(categoryName, endpointData) {
    const category = this.addCategory(categoryName);

    // Validate and normalize endpoint data
    const endpoint = {
      method: endpointData.method || 'GET',
      path: endpointData.path || '',
      description: endpointData.description || '',
      pathParameters: this.normalizeParameters(endpointData.pathParameters),
      queryParameters: this.normalizeParameters(endpointData.queryParameters),
      requestBody: endpointData.requestBody || null,
      responseBody: endpointData.responseBody || null,
      examples: {
        request: endpointData.examples?.request || null,
        response: endpointData.examples?.response || null
      }
    };

    category.endpoints.push(endpoint);
  }

  /**
   * Normalize parameter array
   * @param {Array} parameters - Raw parameters
   * @returns {Array} Normalized parameters
   */
  normalizeParameters(parameters) {
    if (!parameters || !Array.isArray(parameters)) {
      return [];
    }

    return parameters.map(param => ({
      name: param.name || '',
      type: param.type || 'string',
      required: param.required === true,
      description: param.description || '',
      default: param.default !== undefined ? param.default : null
    })).filter(p => p.name); // Only include parameters with names
  }

  /**
   * Convert to JSON object
   * @returns {Object} JSON representation
   */
  toJSON() {
    return {
      version: this.version,
      lastUpdated: this.lastUpdated,
      baseUrl: this.baseUrl,
      categories: this.categories
    };
  }

  /**
   * Load from JSON object
   * @param {Object} json - JSON object
   * @returns {APISpecification} New instance
   */
  static fromJSON(json) {
    const spec = new APISpecification();
    spec.version = json.version;
    spec.lastUpdated = json.lastUpdated;
    spec.baseUrl = json.baseUrl || spec.baseUrl;
    spec.categories = json.categories || [];
    return spec;
  }

  /**
   * Get statistics
   * @returns {Object} Statistics
   */
  getStats() {
    const stats = {
      totalCategories: this.categories.length,
      totalEndpoints: 0,
      endpointsByMethod: {},
      endpointsByCategory: {}
    };

    this.categories.forEach(category => {
      stats.totalEndpoints += category.endpoints.length;
      stats.endpointsByCategory[category.name] = category.endpoints.length;

      category.endpoints.forEach(endpoint => {
        const method = endpoint.method || 'UNKNOWN';
        stats.endpointsByMethod[method] = (stats.endpointsByMethod[method] || 0) + 1;
      });
    });

    return stats;
  }

  /**
   * Find endpoint by method and path
   * @param {string} method - HTTP method
   * @param {string} path - Endpoint path
   * @returns {Object|null} Endpoint or null
   */
  findEndpoint(method, path) {
    for (const category of this.categories) {
      const endpoint = category.endpoints.find(
        e => e.method === method && e.path === path
      );
      if (endpoint) {
        return { category: category.name, ...endpoint };
      }
    }
    return null;
  }

  /**
   * Validate specification completeness
   * @returns {Object} Validation results
   */
  validate() {
    const issues = [];
    const warnings = [];

    if (!this.version) {
      issues.push('Missing version information');
    }

    if (this.categories.length === 0) {
      issues.push('No categories defined');
    }

    this.categories.forEach(category => {
      if (!category.name) {
        issues.push('Category missing name');
      }

      if (category.endpoints.length === 0) {
        warnings.push(`Category "${category.name}" has no endpoints`);
      }

      category.endpoints.forEach((endpoint, index) => {
        const location = `${category.name} > endpoint[${index}]`;

        if (!endpoint.method) {
          issues.push(`${location}: Missing HTTP method`);
        }

        if (!endpoint.path) {
          issues.push(`${location}: Missing endpoint path`);
        }

        if (!endpoint.description) {
          warnings.push(`${location}: Missing description`);
        }

        // Check for path parameters in path but not documented
        const pathParamMatches = (endpoint.path || '').match(/\{([^}]+)\}/g);
        if (pathParamMatches && pathParamMatches.length > 0) {
          const documentedParams = new Set(
            (endpoint.pathParameters || []).map(p => p.name)
          );

          pathParamMatches.forEach(match => {
            const paramName = match.slice(1, -1); // Remove { and }
            if (!documentedParams.has(paramName)) {
              warnings.push(
                `${location}: Path parameter {${paramName}} not documented`
              );
            }
          });
        }
      });
    });

    return {
      valid: issues.length === 0,
      issues,
      warnings
    };
  }
}

/**
 * Parse navigation structure into categories
 * @param {Object} navigation - Navigation structure from extractor
 * @param {APISpecification} spec - API specification to populate
 */
export function parseNavigation(navigation, spec) {
  navigation.categories.forEach(navCategory => {
    const category = spec.addCategory(navCategory.name);

    // Store endpoints for later detail extraction
    navCategory.endpoints.forEach(endpoint => {
      // Add placeholder endpoint
      spec.addEndpoint(navCategory.name, {
        method: endpoint.method || 'GET',
        path: endpoint.path || '',
        description: endpoint.name || '',
        pathParameters: [],
        queryParameters: [],
        requestBody: null,
        responseBody: null,
        examples: {}
      });
    });
  });

  // Handle uncategorized endpoints
  if (navigation.uncategorized && navigation.uncategorized.length > 0) {
    navigation.uncategorized.forEach(endpoint => {
      spec.addEndpoint('Other', {
        method: endpoint.method || 'GET',
        path: endpoint.path || '',
        description: endpoint.name || '',
        pathParameters: [],
        queryParameters: [],
        requestBody: null,
        responseBody: null,
        examples: {}
      });
    });
  }
}

/**
 * Merge detailed endpoint data into specification
 * @param {APISpecification} spec - API specification
 * @param {Array} endpointDetails - Array of detailed endpoint data
 * @param {string} categoryName - Category name
 */
export function mergeEndpointDetails(spec, endpointDetails, categoryName) {
  const category = spec.categories.find(c => c.name === categoryName);
  if (!category) {
    console.warn(`Category "${categoryName}" not found in specification`);
    return;
  }

  endpointDetails.forEach(details => {
    // Find matching endpoint by method and path
    const endpoint = category.endpoints.find(
      e => e.method === details.method && e.path === details.path
    );

    if (endpoint) {
      // Merge details
      Object.assign(endpoint, {
        description: details.description || endpoint.description,
        pathParameters: details.pathParameters || endpoint.pathParameters,
        queryParameters: details.queryParameters || endpoint.queryParameters,
        requestBody: details.requestBody || endpoint.requestBody,
        responseBody: details.responseBody || endpoint.responseBody,
        examples: details.examples || endpoint.examples
      });
    } else {
      console.warn(
        `Endpoint ${details.method} ${details.path} not found in category "${categoryName}"`
      );
    }
  });
}
